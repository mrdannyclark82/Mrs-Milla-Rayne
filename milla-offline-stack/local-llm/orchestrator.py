import os
import sys
from dotenv import load_dotenv
from ollama import Client, ResponseError

# Load environment variables
load_dotenv()

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "gemma2:2b")

class LLMOrchestrator:
    def __init__(self, host=OLLAMA_HOST, default_model=DEFAULT_MODEL):
        self.client = Client(host=host)
        self.default_model = default_model

    def is_service_online(self) -> bool:
        """Checks if the Ollama local service is up and reachable."""
        try:
            # Try to list local models as a healthcheck
            self.client.list()
            return True
        except Exception:
            return False

    def pull_model(self, model_name: str = None) -> bool:
        """Pulls the specified model from the Ollama registry."""
        model = model_name or self.default_model
        print(f"Pulling model '{model}'... (this may take a few minutes if not cached)", file=sys.stderr)
        try:
            self.client.pull(model)
            print(f"Successfully pulled model '{model}'", file=sys.stderr)
            return True
        except Exception as e:
            print(f"Failed to pull model '{model}': {e}", file=sys.stderr)
            return False

    def list_local_models(self):
        """Lists all downloaded models on this Ollama host."""
        try:
            models_data = self.client.list().get('models', [])
            return [m.get('model') or m.get('name') for m in models_data if m]
        except Exception as e:
            print(f"Error listing models: {e}", file=sys.stderr)
            return []

    def generate(self, prompt: str, system_prompt: str = None, model_name: str = None) -> str:
        """Generates a text completion for the given prompt."""
        model = model_name or self.default_model
        
        if not self.is_service_online():
            raise ConnectionError(
                f"Ollama service is offline at {OLLAMA_HOST}. "
                "Please start Ollama (e.g. run 'ollama serve' or start the Ollama desktop app)."
            )

        # Pull model if not already downloaded
        local_models = self.list_local_models()
        if not any(model in name for name in local_models if name):
            success = self.pull_model(model)
            if not success:
                raise RuntimeError(f"Could not load or pull model '{model}'")

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        try:
            response = self.client.chat(model=model, messages=messages)
            return response['message']['content']
        except ResponseError as e:
            print(f"Ollama API Error: {e}", file=sys.stderr)
            raise e

if __name__ == "__main__":
    # Standard CLI test loop
    import argparse
    parser = argparse.ArgumentParser(description="Milla local LLM orchestrator test client.")
    parser.add_argument("prompt", type=str, nargs="?", help="The prompt to send to the local LLM.")
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL, help=f"The Ollama model to use (default: {DEFAULT_MODEL}).")
    parser.add_argument("--system", type=str, default="You are Milla Rayne, a sharp and helpful assistant.", help="The system prompt.")
    
    args = parser.parse_args()
    
    orchestrator = LLMOrchestrator(default_model=args.model)
    
    if not orchestrator.is_service_online():
        print(f"[-] Ollama service is offline at {OLLAMA_HOST}.", file=sys.stderr)
        print("To install Ollama, run: curl -fsSL https://ollama.com/install.sh | sh", file=sys.stderr)
        print("Then run: ollama serve", file=sys.stderr)
        sys.exit(1)
        
    print("[+] Ollama service is online.", file=sys.stderr)
    
    if args.prompt:
        try:
            print(f"\nPrompt: {args.prompt}")
            print(f"Model: {args.model}")
            print("Generating response...\n" + "-"*40)
            response = orchestrator.generate(args.prompt, system_prompt=args.system, model_name=args.model)
            print(response)
            print("-"*40)
        except Exception as e:
            print(f"[-] Generation failed: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        print("[*] No prompt provided. List of local models available:")
        models = orchestrator.list_local_models()
        for m in models:
            print(f" - {m}")
