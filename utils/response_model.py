from typing import Optional, Any

from pydantic import BaseModel


# 响应模版，使用pydantic的BaseModel校验数据类型
class ResponseModel(BaseModel):
    code: int
    message: str
    data: Optional[Any] = None


def response_model(code, data, message):
    return ResponseModel(code=code, data=data, message=message)


# error响应
def error():
    return response_model(400, None, "error")


# error响应，输入错误message
def error_message(message):
    return response_model(400, None, message)


# error响应，输入错误data
def error_data(data):
    return response_model(400, data, "error")


# error响应，输入错误data，错误message
def error_data_message(data, message):
    return response_model(400, data, message)


# success响应
def success():
    return response_model(200, None, "success")


# success响应，输入data
def success_data(data):
    return response_model(200, data, "success")


# success响应，成功message
def success_message(message):
    return response_model(200, None, message)


# success响应，输入data，成功message
def success_data_message(data, message):
    return response_model(200, data, message)
