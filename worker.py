import argparse
import os

import bson
import pika
from demucs.apply import apply_model
from demucs.audio import AudioFile, save_audio
from demucs.pretrained import get_model
from pydub import AudioSegment

# Upload directory
uploadDir = f"./{os.getpid()}_received"
if not os.path.isdir(uploadDir):
    os.makedirs(uploadDir)

# Process result dir
processedDir = f"./{os.getpid()}_processed"
if not os.path.isdir(processedDir):
    os.makedirs(processedDir)

# Demucs model
model = get_model(name='htdemucs')
model.cpu()
model.eval()

# Received message
# data = {
#   "job_id": app.jobID,
#   "instruments": str(instruments.instruments),
#   "audio": {
#       "sample_width": chunk.sample_width,
#       "frame_rate": chunk.frame_rate,
#       "channels": chunk.channels,
#       "format": os.path.splitext(chunkFileName)[1][1:],
#       "data": str(base64.b64encode(chunk.raw_data))
#    }
# }
#
# To server message
# returnMessage = {
#    "job_id": data["job_id"],
#    "audio": {
#       "sample_width":data["audio"]["sample_width"],
#       "frame_rate":data["audio"]["frame_rate"],
#       "channels":data["audio"]["channels"],
#       "format": os.path.splitext(chunkFileName)[1][1:],
#       "data": str(base64.b64encode(overlay.raw_data))
#    }
# }
#


def process_music(ch, method, properties, body):
    data = bson.loads(body)
    print(f'[+] Worker {os.getpid()} received job {data["job_id"]}')

    # Write audio to temporary file
    audio_segment = AudioSegment(
        data=data["audio"]["data"],
        sample_width=data["audio"]["sample_width"],
        frame_rate=data["audio"]["frame_rate"],
        channels=data["audio"]["channels"]
    )
    audioFilePath = f'{uploadDir}/{data["job_id"]}'
    audio_segment.export(audioFilePath, format=data["audio"]["format"])

    # load the audio file
    audioFile = AudioFile(audioFilePath).read(
        streams=0,
        samplerate=model.samplerate,
        channels=model.audio_channels
    )
    ref = audioFile.mean(0)
    audioFile = (audioFile - ref.mean()) / ref.std()

    # Delete temporary file
    os.remove(audioFilePath)

    # apply the model
    sources = apply_model(model,
                          audioFile[None],
                          device='cpu',
                          progress=True,
                          num_workers=1)[0]
    sources = sources * ref.std() + ref.mean()

    # store the model
    instruments = []
    for source, name in zip(sources, model.sources):
        stem = f'{processedDir}/{data["job_id"]}_{name}.{data["audio"]["format"]}'
        save_audio(source, str(stem), samplerate=model.samplerate)
        temp = AudioSegment.from_file(stem)
        instruments.append({
            "name": name,
            "track": temp.raw_data
        })

    # Cleaning all processed files
    file_list = os.listdir(processedDir)
    for file_name in file_list:
        file_path = os.path.join(processedDir, file_name)
        try:
            if os.path.isfile(file_path):
                os.remove(file_path)
        except Exception as e:
            print("error deleting the processed files ", e)

    # Construct message to return combined audio
    returnMessage = {
        "music_id": data["music_id"],
        "job_id": data["job_id"],
        "audio": {
            "sample_width": data["audio"]["sample_width"],
            "frame_rate": data["audio"]["frame_rate"],
            "channels": data["audio"]["channels"],
            "format": data["audio"]["format"],
            "tracks": instruments
        }
    }

    # Return combined audio to server
    print('[!] Chunk processing completed!')
    channelResults.basic_publish(
        exchange="",
        routing_key="result_queue",
        body=bson.dumps(returnMessage),
        properties=pika.BasicProperties(
            delivery_mode=pika.spec.PERSISTENT_DELIVERY_MODE
        ),
    )
    print('[+] Chunk returned.')


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument("-server", type=str,
                        help="Server IP address", default="127.0.0.1")
    args = parser.parse_args()

    print(f'[*] Connecting to RabbitMQ server at {args.server}:5672')

    # Create new connection to RabbitMQ
    connection = pika.BlockingConnection(
        pika.ConnectionParameters(host=args.server, port=5672, socket_timeout=None))

    global channelMusic
    channelMusic = connection.channel()
    channelMusic.queue_declare(queue='job_queue', durable=True)

    global channelResults
    channelResults = connection.channel()
    channelResults.queue_declare(queue='result_queue', durable=True)

    channelMusic.basic_consume(
        queue='job_queue', on_message_callback=process_music)

    print(
        f'[*] Worker with PID {os.getpid()} waiting for music. To exit press CTRL+C')

    channelMusic.start_consuming()
