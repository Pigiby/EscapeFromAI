import json
import uuid
import urllib.request
import urllib.parse
from websocket import create_connection
import random
from pathlib import Path
import shutil

BASE_DIR = Path(__file__).parent
GESTURE_DIR = BASE_DIR / "gesture_recognition"

class ComfyUIClient:
    def __init__(self, server_address="localhost:8000"):
        self.server_address = server_address
        self.client_id = str(uuid.uuid4())

    def queue_prompt(self, workflow):
        payload = {
            "prompt": workflow,
            "client_id": self.client_id
        }

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"http://{self.server_address}/prompt",
            data=data,
            headers={"Content-Type": "application/json"}
        )

        with urllib.request.urlopen(req) as response:
            return json.loads(response.read())

    def wait_for_completion(self, prompt_id):
        ws = create_connection(
            f"ws://{self.server_address}/ws?clientId={self.client_id}"
        )

        try:
            while True:
                message = json.loads(ws.recv())

                if message.get("type") == "executing":
                    data = message.get("data", {})
                    if (
                        data.get("node") is None
                        and data.get("prompt_id") == prompt_id
                    ):
                        break
        finally:
            ws.close()

    def run_workflow(
        self,
        workflow_file,
        prompt_text,
        input_image,
        output_prefix
    ):
        with open(workflow_file, "r", encoding="utf-8") as f:
            workflow = json.load(f)

        # Update workflow nodes
        workflow["17"]["inputs"]["image"] = input_image
        workflow["23"]["inputs"]["text"] = prompt_text
        workflow["9"]["inputs"]["filename_prefix"] = output_prefix
        workflow["3"]["inputs"]["seed"] = random.randint(0, 2**64 - 1)

        result = self.queue_prompt(workflow)
        prompt_id = result["prompt_id"]

        print(f"Prompt queued: {prompt_id}")
        self.wait_for_completion(prompt_id)
        print("Generation completed!")

        return prompt_id

    def get_image(self, filename, subfolder, folder_type):
        params = urllib.parse.urlencode({
            "filename": filename,
            "subfolder": subfolder,
            "type": folder_type
        })

        with urllib.request.urlopen(
            f"http://{self.server_address}/view?{params}"
        ) as response:
            return response.read()

    def get_history(self, prompt_id):
        with urllib.request.urlopen(
            f"http://{self.server_address}/history/{prompt_id}"
        ) as response:
            return json.loads(response.read())


def load_prompts(json_file):
    with open(json_file, "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    labels = [
        "Closed_Fist",
        "Open_Palm",
        "Pointing_Up",
        "Thumb_Down",
        "Thumb_Up",
        "Victory",
        "ILoveYou",
    ]

    prompts = load_prompts(GESTURE_DIR / "prompts.json")

    sequence = [random.randint(1, 7) for _ in range(3)]

    print("\nRandom sequence selected:")
    for i, s in enumerate(sequence, start=1):
        print(f"{i}. {labels[s - 1]}")

    client = ComfyUIClient()

    # --- CLEANUP SECTION ---
    output_dir = GESTURE_DIR / "static" / "assets" / "image_sequence"
    if output_dir.exists():
        print(f"\nChecking if a sequence already exists in {output_dir}...")
        # Option A: Delete the whole folder and recreate it
        #shutil.rmtree(output_dir)
    
    output_dir.mkdir(parents=True, exist_ok=True)
    # -----------------------
    # Check if a sequence already exists (in case we want to keep old ones, but just warn the user)
    existing_images = list(output_dir.glob("*.png"))
    if existing_images == []:
        print("\nGenerating image sequence...")

        for idx, choice in enumerate(sequence, start=1):
            selected_label = labels[choice - 1]
            prompt_data = prompts[str(choice)]

            print(f"\n[{idx}/3] Generating: {selected_label}")

            prompt_id = client.run_workflow(
                workflow_file=GESTURE_DIR / "image_generation.json",
                prompt_text=prompt_data["positive_prompt"],
                input_image=f"{selected_label}.png",
                output_prefix=f"{selected_label}_{idx}"
            )

            history = client.get_history(prompt_id)[prompt_id]

            for node_output in history["outputs"].values():
                if "images" not in node_output:
                    continue

                image = node_output["images"][0]

                image_data = client.get_image(
                    image["filename"],
                    image["subfolder"],
                    image["type"]
                )

                local_path = output_dir / f"{selected_label}_{idx}.png"

                with open(local_path, "wb") as f:
                    f.write(image_data)

                print(f"Saved: {local_path.resolve()}")
                break

        print("\nDone! Sequence saved in image_sequence/")


if __name__ == "__main__":
    main()