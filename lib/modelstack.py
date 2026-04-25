import boto3
import requests
import json
import yaml




class ModelStack:
    def __init__(self, config):
        self.config = config
        
    @staticmethod
    def from_config(config):
        cls = config.get('class')
        if cls == 'ollama':
            return OllamaModelStack(config)
        if cls == 'bedrock':
            return BedrockModelStack(config)
        raise ValueError(f"Unsupported model stack class: {cls}")
    
    def query(self, prompt):
        raise NotImplementedError("Subclasses must implement this method.")




class OllamaModelStack(ModelStack):
    def __init__(self, config):
        super().__init__(config)
        
    def query(self, prompt):
        OLLAMA_HOST = self.config['host']
        model = self.config['model']
        url = f'{OLLAMA_HOST}/api/generate'
        r = requests.post(url, json={'model': model, 'prompt': prompt, 'stream': False})
        if r.status_code != 200:
            raise Exception(f"Request failed with status code {r.status_code}: {r.text}")
        answer = json.loads(r.text)['response']
        return answer





class BedrockModelStack(ModelStack):
    def __init__(self, config):
        super().__init__(config)
        
    def query(self, prompt):
        model = self.config['model']
        region = self.config.get('region', 'us-west-1')
        max_tokens = self.config.get('max_tokens', 1024)
        temperature = self.config.get('temperature', 0.7)
        top_p = self.config.get('top_p', 1)

        params = {
            "anthropic_version": "bedrock-2023-05-31",  # For Anthropic models; omit for others
            "max_tokens": max_tokens,
            "messages": [  # Or use "prompt" for non-chat models like Llama
                {"role": "user", "content": prompt}
            ]
        }    
        
        # Can only be one of these.
        if temperature:
            params['temperature'] = temperature
        elif top_p:
            params['top_p'] = top_p
            
        body = json.dumps(params)
    
        client = boto3.client('bedrock-runtime', region_name=region)
        response = client.invoke_model(
            modelId=model,
            body=body,
            contentType='application/json',
            accept='application/json'
        )
    
        # Parse the response body
        response_body = json.loads(response['body'].read())
    
        # Extract generated text (adjust based on model)
        if 'content' in response_body:  # For Anthropic-style
            answer = response_body['content'][0]['text']
        elif 'generation' in response_body:  # For Amazon Titan or others
            answer = response_body['generation']
        else:
            answer = response_body.get('text', 'No output found')
        
        return answer  # Or return full response_body for more details


class TEMPLATE_ModelStack(ModelStack):
    def __init__(self, config):
        super().__init__(config)
        
    def query(self, prompt):
        answer = "..."
        return answer




def test1():
    config = {
        'class': 'ollama',  
        'host':'http://localhost:11434',
        'model': 'tinyllama:1.1b'
    }
    modelstack = ModelStack.from_config(config)
    print(modelstack.query("What city was Benjamin Franklin born in?"))


def test2():
    config = {
        'class': 'bedrock',  
        'model': 'us.anthropic.claude-haiku-4-5-20251001-v1:0',
        "temperature": 0.7,
        "region": "us-west-1"
    }
    modelstack = ModelStack.from_config(config)
    print(modelstack.query("What city was Benjamin Franklin born in?"))


if __name__ == "__main__":
    test1()
    test2()
