def prepare_service_stage(**kwargs):
    pause = {
        "type": "pause",
        "start": ""
    }
    pause.update(kwargs)
    return pause
