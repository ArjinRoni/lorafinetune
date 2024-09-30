import json
import requests
from flask import Flask, request, jsonify
import base64
import io
from PIL import Image
import random
import urllib3
import time
import logging
from requests.packages.urllib3.exceptions import InsecureRequestWarning

# Disable SSL warnings
urllib3.disable_warnings(InsecureRequestWarning)

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)

app = Flask(__name__)

COMFY_URL = "http://127.0.0.1:8188"

def queue_prompt(workflow):
    p = {"prompt": workflow}
    logging.debug(f"Queueing prompt: {p}")
    try:
        response = requests.post(f"{COMFY_URL}/prompt", json=p, verify=False)
        response.raise_for_status()
        logging.debug(f"Queue prompt response: {response.status_code} - {response.text}")
        return response.json()
    except requests.RequestException as e:
        logging.error(f"Error queueing prompt: {e}")
        raise

def get_image(filename, subfolder, folder_type):
    data = {"filename": filename, "subfolder": subfolder, "type": folder_type}
    logging.debug(f"Fetching image with params: {data}")
    try:
        response = requests.get(f"{COMFY_URL}/view", params=data, verify=False)
        response.raise_for_status()
        logging.debug(f"Get image response: {response.status_code}")
        return response.content
    except requests.RequestException as e:
        logging.error(f"Error fetching image: {e}")
        raise

def upload_image(image_data, image_name):
    files = {
        'image': (image_name, image_data, 'image/png')
    }
    logging.debug(f"Uploading image: {image_name}")
    try:
        response = requests.post(f"{COMFY_URL}/upload/image", files=files, verify=False)
        response.raise_for_status()
        logging.debug(f"Upload image response: {response.status_code} - {response.text}")
        return response.json()
    except requests.RequestException as e:
        logging.error(f"Error uploading image: {e}")
        raise

@app.route('/replace_background', methods=['POST'])
def replace_background():
    logging.debug("Received /replace_background request")
    data = request.json

    prompt_style = data.get('prompt_style', '')
    prompt_main = data.get('prompt_main', '')
    classification_token = data.get('classification_token', '')
    image_base64 = data.get('imageBase64', '')

    logging.debug(f"prompt_style: {prompt_style}")
    logging.debug(f"prompt_main: {prompt_main}")
    logging.debug(f"classification_token: {classification_token}")
    logging.debug(f"image_base64 length: {len(image_base64)}")

    if not image_base64:
        logging.error("Image base64 data is missing")
        return jsonify({'error': 'Image base64 data is required'}), 400

    # Load the workflow
    try:
        with open('bg_workflow.json', 'r') as f:
            file_content = f.read()
            logging.debug(f"bg_workflow.json content length: {len(file_content)}")
            if not file_content.strip():
                logging.error("Workflow file is empty")
                return jsonify({'error': 'Workflow file is empty'}), 500
            workflow = json.loads(file_content)
            logging.debug("Workflow JSON loaded successfully")
    except FileNotFoundError:
        logging.error("Workflow file not found")
        return jsonify({'error': 'Workflow file not found'}), 500
    except json.JSONDecodeError as e:
        logging.error(f"Invalid JSON in workflow file: {str(e)}")
        return jsonify({'error': f'Invalid JSON in workflow file: {str(e)}'}), 500

    # Update the workflow with input data
    try:
        workflow['555']['inputs']['text'] = prompt_style
        workflow['563']['inputs']['text'] = prompt_main
        workflow['204']['inputs']['prompt'] = classification_token
        workflow['625']['inputs']['image'] = image_base64  # Update node 625 with the provided base64 image data
        workflow['607']['inputs']['seed'] = random.randint(0, 2**32 - 1)
        logging.debug("Workflow inputs updated successfully")
    except KeyError as e:
        logging.error(f"Missing key in workflow: {str(e)}")
        return jsonify({'error': f'Missing key in workflow: {str(e)}'}), 500

    # Queue the prompt
    try:
        result = queue_prompt(workflow)
        logging.debug(f"Pipeline queuing result: {result}")
    except requests.RequestException as e:
        logging.error(f"Failed to queue prompt: {str(e)}")
        return jsonify({'error': f'Failed to queue prompt: {str(e)}'}), 500

    if 'error' in result:
        logging.error(f"Error from ComfyUI: {result['error']}")
        return jsonify({'error': result['error']}), 400

    prompt_id = result.get('prompt_id')
    logging.debug(f"Prompt ID received: {prompt_id}")

    if not prompt_id:
        logging.error("No prompt_id returned from ComfyUI")
        return jsonify({'error': 'No prompt_id returned from ComfyUI'}), 500

    # Wait for the image to be generated (with timeout)
    timeout = 300  # 5 minutes
    start_time = time.time()
    while True:
        if time.time() - start_time > timeout:
            logging.error("Image generation timed out")
            return jsonify({'error': 'Image generation timed out'}), 504
        try:
            response = requests.get(f"{COMFY_URL}/history/{prompt_id}", timeout=10, verify=False)
            logging.debug(f"History response: {response.status_code} - {response.text}")
            response.raise_for_status()
            history = response.json()
            if prompt_id in history and len(history[prompt_id]['outputs']) > 0:
                logging.debug("Output found in history")
                break
        except requests.RequestException as e:
            logging.error(f"Failed to check history: {str(e)}")
            return jsonify({'error': f'Failed to check history: {str(e)}'}), 500
        except json.JSONDecodeError as e:
            logging.error(f"Invalid JSON in history response: {str(e)}")
            return jsonify({'error': f'Invalid JSON in history response: {str(e)}'}), 500
        time.sleep(1)

    # Get the output base64 string
    output_node = '630'  # String node containing the base64 output
    try:
        if output_node not in history[prompt_id]['outputs']:
            logging.error(f'Output node {output_node} not found in history')
            return jsonify({'error': f'Output node {output_node} not found in history'}), 500

        output_data = history[prompt_id]['outputs'][output_node]
        logging.debug(f"Output data retrieved: {output_data}")

        if 'string' not in output_data:
            logging.error(f'No string data found in output node {output_node}')
            return jsonify({'error': f'No string data found in output node {output_node}'}), 500

        base64_output = output_data['string']
        logging.debug(f"Base64 output retrieved: {base64_output[:50]}...")  # Log first 50 chars

        # Validate base64 string
        try:
            # Remove metadata prefix if present
            if ',' in base64_output:
                _, base64_str = base64_output.split(',', 1)
            else:
                base64_str = base64_output
            base64.b64decode(base64_str)
            logging.debug("Base64 string is valid")
        except Exception as e:
            logging.error(f'Invalid base64 string in output: {str(e)}')
            return jsonify({'error': 'Invalid base64 string in output'}), 500

        return jsonify({'image': base64_output}), 200

    except Exception as e:
        logging.error(f'Error processing output: {str(e)}')
        return jsonify({'error': f'Error processing output: {str(e)}'}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True, port=5000)
