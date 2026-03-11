import traceback
import sys

try:
    from app.main import app
    print("success")
except Exception as e:
    with open("error_log.txt", "w") as f:
        traceback.print_exc(file=f)
    print("Error saved to error_log.txt")
