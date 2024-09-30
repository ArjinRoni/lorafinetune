import json
import requests
from flask import Flask, request, jsonify
import base64
import io
from PIL import Image
import random
import urllib3
import time
from requests.packages.urllib3.exceptions import InsecureRequestWarning

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

COMFY_URL = "http://127.0.0.1:8188"

def queue_prompt(workflow):
    p = {"prompt": workflow}
    response = requests.post(f"{COMFY_URL}/prompt", json=p)
    return response.json()

def get_image(filename, subfolder, folder_type):
    data = {"filename": filename, "subfolder": subfolder, "type": folder_type}
    response = requests.get(f"{COMFY_URL}/view", params=data)
    return response.content

def upload_image(image_data, image_name):
    files = {
        'image': (image_name, image_data, 'image/png')
    }
    response = requests.post(f"{COMFY_URL}/upload/image", files=files)
    return response.json()

@app.route('/replace_background', methods=['POST'])
def replace_background():
    data = request.json
    prompt_style = data.get('prompt_style', '')
    prompt_main = data.get('prompt_main', '')
    classification_token = data.get('classification_token', '')
    url = data.get('url', '')

    if not url:
        return jsonify({'error': 'URL is required'}), 400

    # Load the workflow
    try:
        with open('bg_workflow.json', 'r') as f:
            workflow = json.load(f)
    except FileNotFoundError:
        return jsonify({'error': 'Workflow file not found'}), 500

    # Update the prompts and URL in the workflow
    workflow['555']['inputs']['text'] = prompt_style
    workflow['563']['inputs']['text'] = prompt_main
    workflow['204']['inputs']['prompt'] = classification_token
    workflow['623']['inputs']['image'] = url  # Update node 623 with the provided URL

    # Generate a random seed
    random_seed = random.randint(0, 2**32 - 1)
    workflow['607']['inputs']['seed'] = random_seed

    # Queue the prompt
    try:
        result = queue_prompt(workflow)
    except requests.RequestException as e:
        return jsonify({'error': f'Failed to queue prompt: {str(e)}'}), 500

    if 'error' in result:
        return jsonify({'error': result['error']}), 400

    prompt_id = result['prompt_id']

    # Wait for the image to be generated (with timeout)
    timeout = 300  # 5 minutes
    start_time = time.time()
    while True:
        if time.time() - start_time > timeout:
            return jsonify({'error': 'Image generation timed out'}), 504
        try:
            response = requests.get(f"{COMFY_URL}/history/{prompt_id}", timeout=10)
            history = response.json()
            if prompt_id in history and len(history[prompt_id]['outputs']) > 0:
                break
        except requests.RequestException as e:
            return jsonify({'error': f'Failed to check history: {str(e)}'}), 500
        time.sleep(1)

    # Get the output image
    output_node = '619'  # SaveImage node
    if output_node in history[prompt_id]['outputs']:
        output_images = history[prompt_id]['outputs'][output_node]['images']
        if output_images:
            try:
                image_data = get_image(output_images[0]['filename'], output_images[0]['subfolder'], 'output')
                image = Image.open(io.BytesIO(image_data))
                buffered = io.BytesIO()
                image.save(buffered, format="PNG")
                img_str = base64.b64encode(buffered.getvalue()).decode()
                return jsonify({'image': img_str})
            except Exception as e:
                return jsonify({'error': f'Failed to process output image: {str(e)}'}), 500

    return jsonify({'error': 'Failed to generate image'}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True, port=5000)
