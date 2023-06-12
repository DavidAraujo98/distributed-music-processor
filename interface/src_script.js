// Show and hide file submission
function optionCheck() {
    var musicSubmission = new bootstrap.Collapse("#musicSubmission", {
        toggle: false,
    });

    var IDField = new bootstrap.Collapse("#IDField", {
        toggle: false,
    });

    var ReturnField = new bootstrap.Collapse("#ReturnField", {
        toggle: false,
    });
    ReturnField.hide();

    var select = document.getElementById("Select");

    index = select.selectedIndex;
    if (index == 1) {
        IDField.hide();
        musicSubmission.show();
    } else if (index == 2 || index == 3 || index == 5) {
        musicSubmission.hide();
        IDField.show();
    } else {
        IDField.hide();
        musicSubmission.hide();
    }
}

// Make REST API request
function makeRequest() {
    console.log("in request function");
    baseUrl = "http://127.0.0.1:8000";
    requestParams = {
        method: "GET",
    };

    bt = document.getElementById("requestButton");
    bt.disabled = true;
    infile = document.getElementById("musicFile");
    infile.disabled = true;

    var select = document.getElementById("Select");
    id = document.getElementById("IDFieldText").value;

    switch (select.selectedIndex) {
        case 0: // Listar todas as músicas submetidas
            baseUrl = baseUrl.concat("/music");
            break;
        case 1: // Adicionar nova música
            baseUrl = baseUrl.concat("/music");
            requestParams.method = "POST";
            musicFile = infile.files[0];
            const payload = new FormData();
            payload.append("musicFile", musicFile);
            requestParams.body = payload;
            break;
        case 2: // Estado de processamento de uma musica
            baseUrl = baseUrl.concat("/music", "/", id);
            break;
        case 3: // Processar uma musica
            requestParams.method = "POST";
            baseUrl = baseUrl.concat("/music", "/", id);
            break;
        case 4: // Listar todos Jobs
            baseUrl = baseUrl.concat("/job");
            break;
        case 5: // Informação sobre um Job
            requestParams.method = "POST";
            baseUrl = baseUrl.concat("/job", "/", id);
            break;
    }

    fetch(baseUrl, requestParams)
        .then((response) => response.json())
        .then((data) => {
            var ReturnField = new bootstrap.Collapse("#ReturnField", {
                toggle: false,
            });
            document.getElementById("ReturnFieldText").value = JSON.stringify(
                data,
                undefined,
                4
            );
            ReturnField.show();
            bt.disabled = false;
            infile.disabled = false;
        })
        .catch((error) => {
            console.log(error);
            bt.disabled = false;
            infile.disabled = false;
        });
}

function resetSystem() {
    console.log("in reset function");
    baseUrl = "http://127.0.0.1:8000/reset";
    requestParams = {
        method: "POST",
    };

    fetch(baseUrl, requestParams); 
}
