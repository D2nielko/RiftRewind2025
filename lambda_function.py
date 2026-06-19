# lambda_function.py
from app import handler

def lambda_handler(event, context):
    return handler(event, context)