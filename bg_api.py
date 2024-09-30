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

COMFY_URL = "http://34.81.132.129:8188"

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
    image_base64 = data.get('imageBase64', '')

    if not image_base64:
        return jsonify({'error': 'Image base64 data is required'}), 400

    # Load the workflow
    try:
        with open('bg_workflow.json', 'r') as f:
            workflow = json.load(f)
    except FileNotFoundError:
        return jsonify({'error': 'Workflow file not found'}), 500
    except json.JSONDecodeError as e:
        return jsonify({'error': f'Invalid JSON in workflow file: {str(e)}'}), 500

    # Update the workflow with input data
    try:
        workflow['555']['inputs']['text'] = prompt_style
        workflow['4']['inputs']['text'] = prompt_main
        workflow['563']['inputs']['text'] = prompt_main
        workflow['204']['inputs']['prompt'] = classification_token
        workflow['625']['inputs']['image'] = image_base64
        workflow['607']['inputs']['seed'] = random.randint(0, 2**32 - 1)
    except KeyError as e:
        return jsonify({'error': f'Missing key in workflow: {str(e)}'}), 500

    # Queue the prompt
    try:
        result = queue_prompt(workflow)
    except requests.RequestException as e:
        return jsonify({'error': f'Failed to queue prompt: {str(e)}'}), 500

    if 'error' in result:
        return jsonify({'error': result['error']}), 400

    prompt_id = result['prompt_id']

    print(f"Queued prompt with ID: {prompt_id}")

    # Wait for the image to be generated (with timeout)
    timeout = 300  # 5 minutes
    start_time = time.time()
    while True:
        if time.time() - start_time > timeout:
            print("Image generation timed out")
            return jsonify({'error': 'Image generation timed out'}), 504
        try:
            response = requests.get(f"{COMFY_URL}/history/{prompt_id}", timeout=10)
            history = response.json()
            print(f"Checking history. Status: {response.status_code}")
            if prompt_id in history:
                print(f"Prompt found in history. Outputs: {list(history[prompt_id]['outputs'].keys())}")
                if len(history[prompt_id]['outputs']) > 0:
                    break
            else:
                print(f"Prompt {prompt_id} not found in history")
        except requests.RequestException as e:
            print(f"Error checking history: {str(e)}")
            return jsonify({'error': f'Failed to check history: {str(e)}'}), 500
        time.sleep(1)

    # After the while loop that waits for the image generation
    output_node = '636'  # Node containing the base64 output
    if output_node in history[prompt_id]['outputs']:
        output_data = history[prompt_id]['outputs'][output_node]
        print(f"Output data for node {output_node}: {output_data.keys()}")
        if 'string' in output_data:
            base64_output = output_data['string']
            
            # Log the result (truncate base64 for readability)
            print(f"Background replacement completed successfully.")
            print(f"Prompt style: {prompt_style}")
            print(f"Prompt main: {prompt_main}")
            print(f"Classification token: {classification_token}")
            print(f"Input image base64 (truncated): {image_base64[:20]}...")
            print(f"Output image base64 (truncated): {base64_output[:20]}...")
            
            return jsonify({
                'success': True,
                'image': base64_output
            })
        else:
            print(f"No 'string' key in output data for node {output_node}")
    else:
        print(f"Output node {output_node} not found in history outputs")

    # If we couldn't find the image data
    print("Failed to generate image. No output found in history.")
    print(f"Available outputs: {history[prompt_id]['outputs'].keys()}")
    return jsonify({
        'success': False,
        'error': 'Failed to generate image'
    }), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True, port=5000)
