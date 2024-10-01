import subprocess
import sys
import os

def run_api(api_file):
    return subprocess.Popen([sys.executable, api_file], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)

def print_logs(process, prefix):
    for line in process.stdout:
        print(f"{prefix}: {line.strip()}")

if __name__ == "__main__":
    bg_api_process = run_api("bg_api.py")
    upscaler_api_process = run_api("upscaler_api.py")

    try:
        print("Both APIs are now running. Press Ctrl+C to stop.")
        print_logs(bg_api_process, "BG API")
        print_logs(upscaler_api_process, "Upscaler API")
    except KeyboardInterrupt:
        print("\nStopping APIs...")
        bg_api_process.terminate()
        upscaler_api_process.terminate()
        bg_api_process.wait()
        upscaler_api_process.wait()
        print("APIs stopped.")
