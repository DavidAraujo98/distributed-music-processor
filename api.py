import argparse
import datetime
import hashlib
import json
import os
import shutil
import time
import threading
from enum import Enum
from typing import List

import bson
import eyed3
import pika
import torch
import uvicorn
from fastapi import FastAPI, HTTPException, UploadFile, status, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from pydub import AudioSegment
from pydub.utils import make_chunks

torch.set_num_threads(1)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# List of all music objects
app.musics = []

# Music and jobs IDs
app.jobID = 0
app.repeat = 0

# Chunk size for workers
chunkSize = 6 * 1000  # 6 seconds

# mp3 upload directory
uploadDir = "./uploads"
if not os.path.isdir(uploadDir):
    os.makedirs(uploadDir)

# mp3 upload directory
returnedDir = "./download"
if not os.path.isdir(returnedDir):
    os.makedirs(returnedDir)


class Instruments(Enum):
    drums = 1
    vocals = 2
    bass = 3
    other = 4


class InstrumentsRequested(BaseModel):
    instruments: List[int]


def getMetadata(filePath):
    file = eyed3.load(filePath)
    metadata = {}
    metadata["name"] = file.tag.title
    metadata["band"] = file.tag.artist
    metadata["album"] = file.tag.album
    return metadata


def splicedAudio(musicPath):
    audioSegment = AudioSegment.from_file(musicPath)
    yield from make_chunks(audioSegment, chunkSize)


def getIntChecksum(data):
    checksum = hashlib.md5(data).hexdigest()
    return int(checksum, 16) % 1000000


@app.post("/music")
def submit(musicFile: UploadFile):
    try:
        # Create new music object
        # Convert file name to relative path

        # This is a stupid way of getting the checksum,
        # but FastAPI likes to complicate.

        temp = str(int(time.time()))
        with open(temp, "wb") as file:
            file.write(musicFile.file.read())

        checksum = ""
        with open(temp, "rb") as file:
            checksum = getIntChecksum(file.read())

        filePath = f"{uploadDir}/{checksum}"        

        os.rename(temp, filePath)
        
        existing = next((x for x in app.musics if x["music_id"] == checksum), None)
        if existing:
            return existing

        # Get audio file metadata
        musicObj = {
            "music_id": checksum,
            "name": musicFile.filename,
            "metadata": getMetadata(filePath),
            "tracks": [
                {"name": x.name, "track_id": x.value} for x in list(Instruments)
            ],
        }

        # Add to the list of musics
        app.musics.append(musicObj)

        return musicObj
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
            detail=f"Invalid input",
        )


@app.get("/music")
def listAll(request: Request):
    return app.musics


@app.post("/music/{music_id}")
def process(music_id: int, instruments: InstrumentsRequested, request: Request):
    # Check if music exists
    music = next((x for x in app.musics if x["music_id"] == music_id), None)
    if music is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Music not found",
        )

    # Check if instrument is available
    if not all(
        list(
            map(lambda x: x in [y.value for y in Instruments], instruments.instruments)
        )
    ):
        raise HTTPException(
            status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
            detail=f"Track not found",
        )

    musicPath = f'{uploadDir}/{music["music_id"]}'

    # Record start time of music processing
    music["processStart"] = time.time()

    if "results" in music.keys():
        previousPath = f'{returnedDir}/{music["results"]["final"].split("/")[-1]}'
        previous = AudioSegment.from_file(previousPath)
        finished = AudioSegment.silent(duration=len(previous))
        
        for instrument in music["results"]["instruments"]:
            path = f'{returnedDir}/{instrument["track"].split("/")[-1]}'
            if instrument["name"] in [Instruments(x).name for x in instruments.instruments]:
                finished = finished.overlay(AudioSegment.from_file(path))
            instrument["track"]=f"{app.hostAddr}{path[1:]}"
        
        extension = music["name"].split(".")[-1]
        finishedPath = f'{returnedDir}/combined_{app.repeat}_{music["music_id"]}.{extension}'
        app.repeat += 1
        finished.export(finishedPath, format=extension)
        
        music["results"]["final"] = f"{app.hostAddr}{finishedPath[1:]}"
        
        result = json.dumps(music["results"])
        result = result.replace("0.0.0.0", request.url.hostname)
        result = json.loads(result)
        return result

    # Split audio in chunk and create new jobs
    audio_chunks = []
    for index, chunk in enumerate(splicedAudio(musicPath)):
        # Create worker message
        message = {
            "music_id": music["music_id"],
            "job_id": app.jobID + index,
            "audio": {
                "sample_width": chunk.sample_width,
                "frame_rate": chunk.frame_rate,
                "channels": chunk.channels,
                "format": os.path.splitext(music["name"])[1][1:],
                "data": chunk.raw_data,
            },
        }

        # Create new job for chunk
        job = {
            "music_id": music["music_id"],
            "job_id": app.jobID + index,
            "status": 0,
            "size": len(chunk.raw_data),
            "time": int(len(chunk) / 1000),
            "track_id": instruments.instruments,
        }
        music.setdefault("jobs", []).append(job)

        # Send to RabbitMQ queue
        channelMusic.basic_publish(
            exchange="",
            routing_key="job_queue",
            body=bson.dumps(message),
            properties=pika.BasicProperties(
                delivery_mode=pika.spec.PERSISTENT_DELIVERY_MODE
            ),
        )

    app.jobID += len(audio_chunks)

    return music


@app.get("/music/{music_id}")
def progress(music_id: int, request: Request):
    music = next((x for x in app.musics if x["music_id"] == music_id), None)
    
    # Check if music exists and is being processed
    if music is None or len(music.get("jobs", [])) == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Music not found",
        )

    completed = sum(job["status"] for job in music["jobs"])
    progress = int(completed / len(music["jobs"]) * 100)

    if progress == 100:
        if music.get("results",None) is None:
            return {"progess": progress, "results": "Results still loading..."}
        
        result = json.dumps(music["results"])
        result = result.replace("0.0.0.0", request.url.hostname)
        result = json.loads(result)
        return result

    return {"progress": progress}


@app.get("/download/{path}")
def download(path: str):
    if not os.path.exists(f"{returnedDir}/{path}"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File not found",
        )
    return FileResponse(path=f"{returnedDir}/{path}", filename=path.split("/")[-1])


@app.get("/job")
def jobs():
    jobs = []
    for music in app.musics:
        if music.get("jobs", None):
            for job in music["jobs"]:
                jobs.append(job["job_id"])
            return jobs
    raise HTTPException(
        status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
        detail=f"Invalid input",
    )


@app.get("/job/{job_id}")
def jobStat(job_id: int):
    for music in app.musics:
        if music.get("jobs", None):
            for job in music["jobs"]:
                if job["job_id"] == job_id:
                    r = dict(job)
                    del r["status"]
                    if r.get("tracksPath", None):
                        del r["tracksPath"]
                    return r
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Music not found",
    )


@app.post("/reset")
def reset():
    if os.path.isdir(uploadDir):
        for file_name in os.listdir(uploadDir):
            file_path = os.path.join(uploadDir, file_name)
            try:
                if os.path.isfile(file_path):
                    os.remove(file_path)
            except Exception as e:
                print("error deleting the uploaded files ", e)
    if os.path.isdir(returnedDir):
        for file_name in os.listdir(returnedDir):
            file_path = os.path.join(returnedDir, file_name)
            try:
                if os.path.isfile(file_path):
                    os.remove(file_path)
            except Exception as e:
                print("error deleting the processed files ", e)
    app.JobID = 0
    app.musics = []


# Thread  waiting for job responses
class ResultListener(threading.Thread):
    def __init__(self, *args, **kwargs):
        super(ResultListener, self).__init__(*args, **kwargs)
        self.connection = pika.BlockingConnection(
            pika.ConnectionParameters(host="0.0.0.0", port=5672, socket_timeout=None)
        )

    def run(self, *args, **kwargs):
        self.channelResults = self.connection.channel()
        self.channelResults.queue_declare(queue="result_queue", durable=True)
        self.channelResults.basic_consume(
            queue="result_queue", on_message_callback=self.receive_result, auto_ack=True
        )
        print("[*] Listening for workers responses...")
        self.channelResults.start_consuming()

    def assemble_result(self, music):
        print(f'[!] All jobs of music {music["music_id"]} have been received! Assembling...')
        
        start = time.time()
        extension = music["name"].split(".")[-1]
        finished = AudioSegment.empty()

        # List of completed
        completedTracks = [{"name": x.name, "track": ""} for x in Instruments]

        # Go through all jobs of a music
        for job in music["jobs"]:
            layers = AudioSegment.empty()
            # Go through all tracks of a job
            for track in job["tracksPath"]:
                audio_segment = AudioSegment.from_file(track["track"])

                # Appending each chunks track to the collective of that track
                existingTrack = next(
                    (x for x in completedTracks if x["name"] == track["name"]), {}
                )
                if existingTrack["track"] != "":
                    existingAudio = AudioSegment.from_file(existingTrack["track"])
                    existingAudio += audio_segment
                    existingAudio.export(existingTrack["track"], format=extension)
                    os.remove(track["track"])
                else:
                    existingTrack["track"] = track["track"]

                # If track is one of the requested, overlays the chunks for final
                if track["name"] in [Instruments(x).name for x in job["track_id"]]:
                    if len(layers) == 0:
                        layers += audio_segment
                    else:
                        layers = layers.overlay(audio_segment)

            # Concatenate to finished music
            finished += layers

        # Construct download links
        completedTracks = list(
            map(
                lambda x: {
                    "name": x["name"],
                    "track": f'{app.hostAddr}{x["track"][1:]}',
                },
                completedTracks,
            )
        )

        finishedPath = f'{returnedDir}/combined_{music["music_id"]}.{extension}'
        finished.export(finishedPath, format=extension)
        music["processingTime(s)"] = round(music["processingTime(s)"] + (time.time() - start), 2)
        
        music["results"] = {
                "progress": 100,
                "processingTime(s)": music["processingTime(s)"],
                "final": f"{app.hostAddr}{finishedPath[1:]}",
                "instruments": completedTracks,
            }
        print(f'[+] Music {music["music_id"]} results are available!')

    def receive_result(self, ch, method, properties, body):
        data = bson.loads(body)
        job_id = data["job_id"]
        print(f"[+] Job {job_id} has been received!")

        # Write audios to track files
        tracks = []
        for track in data["audio"]["tracks"]:
            audio_segment = AudioSegment(
                data=track["track"],
                sample_width=data["audio"]["sample_width"],
                frame_rate=data["audio"]["frame_rate"],
                channels=data["audio"]["channels"],
            )

            # Checksum of new file of track
            checksum = getIntChecksum(audio_segment.raw_data)

            # Record tracks paths
            outTrackPath = (
                f'{returnedDir}/{checksum}_{track["name"]}.{data["audio"]["format"]}'
            )
            tracks.append({"name": track["name"], "track": outTrackPath})

            # Write tracks files
            audio_segment.export(outTrackPath, format=data["audio"]["format"])

        # Update status and save received data from job
        for music in app.musics:
            completed = 0
            for x in music.get("jobs", []):
                if x["job_id"] == job_id:
                    # Update processing time of music
                    music["processingTime(s)"] = time.time() - music["processStart"]
                    # Update job status to complete
                    x["status"] = 1
                    # Record chunk path
                    x["tracksPath"] = tracks
                completed += x["status"]
            if int(completed / len(music["jobs"]) * 100) == 100:
                self.assemble_result(music)
            break


# Job queue connection
connection = pika.BlockingConnection(
    pika.ConnectionParameters(host="0.0.0.0", port=5672, socket_timeout=None)
)
# Worker channel
channelMusic = connection.channel()
channelMusic.queue_declare(queue="job_queue", durable=True)


# Thread declaration
t1 = ResultListener()
# Thread kill trigger
thread_killer = False


# Kill worker listener thread
@app.on_event("shutdown")
def shutdown_event():
    reset()
    t1.connection.close()
    t1.join()
    connection.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    # Start listening for results
    t1.start()
    print("[+] Channel for job delivery started...")

    app.hostAddr = "0.0.0.0:8000"

    # Starting Fast API
    uvicorn.run(app, host="0.0.0.0", port=8000)
