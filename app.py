import os
import re
import fastapi
import requests
from fastapi import FastAPI, Response, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, BeforeValidator, Field, TypeAdapter
from datetime import datetime, timedelta
from uuid import uuid4, UUID
from fastapi.middleware.cors import CORSMiddleware
from typing import Annotated, List, Optional
import motor.motor_asyncio
from dotenv import load_dotenv

load_dotenv()


#

app = FastAPI()

origins = ["https://simple-smart-hub-client.netlify.app/"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
#Might be used in place of line 34 connection
#MONGO_URL = os.environ.get("MONGO_URL")
connection = motor.motor_asyncio.AsyncIOMotorClient(os.getenv("MONGO_URL"))

db = connection.Project

settingsdb = db.Final_Project
sensordb = db.Sensor_Data

PyObjectId = Annotated[str, BeforeValidator(str)]

"""
class Settings(BaseModel):
    id: PyObjectId | None = Field(default=None, alias="_id")
    user_temp: float | None
    user_light: str | None
    light_duration: str | None
    light_time_off: str | None
"""
class Settings(BaseModel):
    id: Optional[PyObjectId]= Field(alias="_id", default=None)
    user_temp: Optional[float]=None
    user_light: Optional[str]= None
    light_duration: Optional[str]= None
    light_time_off: Optional[str]= None

class Settings_Updated(BaseModel):
    id: Optional[PyObjectId]= Field(default=None, alias="_id")
    user_temp: Optional[float]= None
    user_light: Optional[str]= None
    light_time_off: Optional[str]= None

class SensorData(BaseModel):
    id: Optional[PyObjectId]= Field(default=None, alias="_id")
    temperature: Optional[float]= None
    presence: Optional[bool]= None
    datetime: Optional[str]= None

regex = re.compile(r'((?P<hours>\d+?)h)?((?P<minutes>\d+?)m)?((?P<seconds>\d+?)s)?')

def parse_time(time_str):
    parts = regex.match(time_str)
    if not parts:
        return
    parts = parts.groupdict()
    time_params = {}
    for name, param in parts.items():
        if param:
            time_params[name] = int(param)
    return timedelta(**time_params) 

def get_sunset():
    URL = "https://api.sunrisesunset.io/json?lat=17.97787&lng=-76.77339&timezone=UTC&date=1990-05-22&time_format=24"
    response = requests.get(url=URL).json()

    sunset_time = response["results"]["sunset"]
    convert_sun = datetime.strptime(sunset_time, '%H:%M:%S')

    return sunset_time

@app.put("/settings", status_code=201)
async def settings_create(settings: Settings):
    #determine how time should be set for user light
    if settings.user_light == "sunset":
        user_light = datetime.strptime(get_sunset(), "%H:%M:%S")
        settings.user_light = (user_light).strftime("%H:%M:%S")
    else:
        user_light = datetime.strptime(settings.user_light, "%H:%M:%S")

    duration = parse_time(settings.light_duration)
    settings.light_time_off = (user_light + duration).strftime("%H:%M:%S")

    #check if settings is already created and needs to be updated
    #or if a new setting will be created

    #existing_setting = await settingsdb.find().to_list(1)
    existing_setting = await settingsdb.find().to_list(1)

    if len (existing_setting) == 1:
        settingsdb.update_one({"_id": existing_setting[0]["_id"]}, {"$set": settings.model_dump(exclude=["light_duration"])})

        new_setting = await settingsdb.find_one({"_id": existing_setting[0]["_id"]})
        return JSONResponse(status_code=200, content=Settings_Updated(**new_setting).model_dump())
    else:
        settings_para = settings.model_dump(exclude=["light_duration"])
        inserted_settings = await settingsdb.insert_one(settings_para)
        new_setting = await settingsdb.find_one({"_id": inserted_settings.inserted_id})

        return JSONResponse(status_code=201, content=Settings_Updated(**new_setting).model_dump())
        #return JSONResponse(status_code=201, content=Settings_Updated(**new_setting).model_dump())
    
@app.get("/graph", status_code=200)
async def temp_data(size: int = None):
    data = await settingsdb["Final_Project"].find().to_list(size)

    return TypeAdapter(List[SensorData]).validate_python(data)

@app.post("/sensorData", status_code=201)
async def make_SensorData(data: SensorData):
    current_time = datetime.now().strftime("%H:%M:%S")
    data_info = data.model_dump()
    data_info["datetime"] = current_time
    new_entry = await sensordb.insert_one(data_info)
    created_entry = await sensordb.find_one({"_id": new_entry.inserted_id})
###created another database for sensor data
    return SensorData(**created_entry)


@app.get("/fan", status_code=200)
async def fan_con():
    sensor_info = await sensordb.find().to_list(999)
    num = len(sensor_info) - 1
    cur_sensors = sensor_info[num]

    all_settings = await settingsdb.find().to_list(999)
    cur_settings = all_settings[0]

    if (cur_sensors["presence"] == True):
        if (cur_sensors["temperature"] >= cur_settings["user_temp"]):
            fanState = True
        else:
            fanState = False
    else:
        fanState = False

    FanStatus = { "fan": fanState}

    return FanStatus

@app.get("/light", status_code=200)
async def light_con():
    sensor_info = await sensordb.find().to_list(999)
    num = len(sensor_info) - 1
    cur_sensors = sensor_info[num]

    all_settings = await settingsdb.find().to_list(999)
    cur_settings = all_settings[0]

    set_start_time = datetime.strptime(cur_settings["user_light"], '%H:%M:%S')
    set_end_time = datetime.strptime(cur_settings["light_time_off"], '%H:%M:%S')
    current_time = datetime.strptime(cur_sensors["datetime"], '%H:%M:%S')

    if (cur_sensors["presence"] == True):
        if ((current_time>set_start_time) & (current_time<set_end_time)):
            lightState = True
        else:
            lightState = False
    else:
        lightState = False

    LightStatus = { "light": lightState}

    return LightStatus


