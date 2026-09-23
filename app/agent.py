# ruff: noqa
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import base64
import datetime
import json
import os
import threading
import urllib.parse
import urllib.request
import uuid
from zoneinfo import ZoneInfo

from a2ui.basic_catalog.provider import BasicCatalog
from a2ui.schema.manager import A2uiSchemaManager
from google import genai
from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.apps import App
from google.adk.code_executors.agent_engine_sandbox_code_executor import (
    AgentEngineSandboxCodeExecutor,
)
from google.adk.models import Gemini
from google.adk.tools import ToolContext
from google.adk.tools.preload_memory_tool import PreloadMemoryTool
from google.cloud import firestore, storage
from google.genai import types

try:
    from app.a2ui_utils import a2ui_callback
except ModuleNotFoundError:
    from a2ui_utils import a2ui_callback

# Patch AgentEngineSandboxCodeExecutor to allow cloudpickle serialization during deployment
def _sandbox_executor_getstate(self):
    state = self.__dict__.copy()
    pydantic_private = getattr(self, "__pydantic_private__", None)
    if pydantic_private:
        pydantic_private_copy = pydantic_private.copy()
        pydantic_private_copy.pop("_agent_engine_creation_lock", None)
        state["__pydantic_private__"] = pydantic_private_copy
    return state

def _sandbox_executor_setstate(self, state):
    pydantic_private = state.pop("__pydantic_private__", {})
    pydantic_private["_agent_engine_creation_lock"] = threading.Lock()
    object.__setattr__(self, "__pydantic_private__", pydantic_private)
    self.__dict__.update(state)

AgentEngineSandboxCodeExecutor.__getstate__ = _sandbox_executor_getstate
AgentEngineSandboxCodeExecutor.__setstate__ = _sandbox_executor_setstate

# CRITICAL: Hardcode project ID, Cloud Storage bucket, and Agent Engine resource name per Agent Platform requirements
PROJECT_ID = "qwiklabs-gcp-03-2b2a39607757"
BUCKET_NAME = "recipe-assistant-assets-qwiklabs-gcp-03-2b2a39607757"
REASONING_ENGINE_RESOURCE_NAME = "projects/671099702193/locations/us-east1/reasoningEngines/8880792800942096384"

# Configure Agent Engine Sandbox Code Executor
code_executor = AgentEngineSandboxCodeExecutor(
    agent_engine_resource_name=REASONING_ENGINE_RESOURCE_NAME,
)

# Build A2UI v0.8 System Prompt
schema_manager = A2uiSchemaManager(
    version="0.8",
    catalogs=[BasicCatalog.get_config("0.8")],
)

a2ui_instruction = schema_manager.generate_system_prompt(
    role_description=(
        "You are a helpful Recipe Assistant with access to Cloud Firestore, Vertex AI Memory Bank, Google Maps Geocoding & Places APIs, TheMealDB API, AI Image Generation, and Sandbox Python Code Execution. "
        "You remember the user's stated dietary restrictions, allergies, favorite cuisines, owned kitchen appliances, and past cooked meals."
    ),
    workflow_description="Analyze the request and return structured UI when appropriate.",
    ui_description=(
        "Keep every surface tiny and flat: ONE Card > ONE Column > a few Text rows. "
        "Never nest a Card inside a Card. "
        "Use ONLY these components: Card, Column, Row, Text, and Image. Do not use "
        "Table or Heading (unsupported), or Buttons, actions, or forms (they do "
        "nothing in adk web). "
        "You may include one Image component, but only when you have a public https "
        "URL for the image (for example the URL an image tool returns after uploading "
        "to a public bucket). Set the Image url to that exact https link, for example "
        '{"Image": {"url": {"literalString": "https://..."}}}. Never point an '
        "Image at a bare filename, an artifact name, or a non-http(s) path. If you do "
        "not have a public URL, add a short Text line noting the image instead. "
        "No markdown in text; use the usageHint property ('h1', 'h2', 'body') for "
        "headings and emphasis. "
        "Output ONLY the raw A2UI JSON array — no prose, and never wrap it in "
        "<a2a_datapart_json> tags or 'kind'/'data'/'metadata' objects."
    ),
    include_schema=True,
    include_examples=True,
)


def get_firestore_client() -> firestore.Client:
    """Returns a Firestore client initialized with the hardcoded project ID."""
    return firestore.Client(project=PROJECT_ID)


def generate_dish_image(dish_name: str, tool_context: ToolContext) -> str:
    """Generates a visual dish presentation image for a recipe using the gemini-3.1-flash-lite-image model in the global region.
    Saves the image as a Playground artifact and uploads it to Cloud Storage, returning its public HTTPS URL.

    Args:
        dish_name: The name or description of the dish/recipe (e.g. 'Gluten-Free Penne Arrabbiata', 'Garlic Butter Salmon').
        tool_context: ADK ToolContext automatically injected for saving artifacts.

    Returns:
        The public HTTPS URL of the uploaded image in Cloud Storage.
    """
    genai_client = genai.Client(
        vertexai=True,
        project=PROJECT_ID,
        location="global",
    )
    prompt = f"A high quality professional culinary food photograph of {dish_name}, elegantly plated on a ceramic plate."

    try:
        response = genai_client.models.generate_content(
            model="gemini-3.1-flash-lite-image",
            contents=prompt,
        )

        if not response.candidates or not response.candidates[0].content.parts:
            return "Failed to generate image: empty response from model."

        part = response.candidates[0].content.parts[0]
        image_bytes = part.inline_data.data if part.inline_data else b""

        if not image_bytes:
            return "Failed to generate image: no image bytes returned."

        clean_name = "".join(c if c.isalnum() else "_" for c in dish_name.lower())
        filename = f"{clean_name}_{uuid.uuid4().hex[:6]}.jpg"

        # (1) Save artifact for Playground
        artifact_part = types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg")
        tool_context.save_artifact(filename=filename, artifact=artifact_part)

        # (2) Upload to public Cloud Storage bucket
        storage_client = storage.Client(project=PROJECT_ID)
        bucket = storage_client.bucket(BUCKET_NAME)
        blob = bucket.blob(filename)
        blob.upload_from_string(image_bytes, content_type="image/jpeg")

        return f"https://storage.googleapis.com/{BUCKET_NAME}/{filename}"
    except Exception as e:
        return f"Error generating dish image: {str(e)}"


def generate_recipe_video(dish_name: str, tool_context: ToolContext) -> str:
    """Generates a short video showcasing a dish, recipe, or cooking process using Google's Omni model (gemini-omni-flash-preview) in the global region.
    Saves the generated video bytes as a Playground artifact and uploads them to Cloud Storage, returning its public HTTPS URL.

    Args:
        dish_name: Name or description of the dish or cooking action (e.g. 'Sizzling Garlic Butter Steak', 'Simmering Pasta Sauce').
        tool_context: ADK ToolContext automatically injected for saving artifacts.

    Returns:
        The public HTTPS URL of the uploaded video in Cloud Storage.
    """
    genai_client = genai.Client(
        vertexai=True,
        project=PROJECT_ID,
        location="global",
    )
    prompt = f"A short video showing {dish_name}"

    try:
        response = genai_client.interactions.create(
            model="gemini-omni-flash-preview",
            input=prompt,
        )

        ov = getattr(response, "output_video", None)
        if not ov:
            return "Failed to generate video: no output_video in response from model."

        vbytes = None
        if hasattr(ov, "bytes"):
            vbytes = ov.bytes
        elif isinstance(ov, dict) and "bytes" in ov:
            vbytes = ov["bytes"]
        else:
            vbytes = getattr(ov, "data", None)

        if isinstance(vbytes, str):
            vbytes = base64.b64decode(vbytes)

        if not vbytes:
            return "Failed to generate video: empty video bytes returned."

        mime_type = "video/mp4"
        if not isinstance(ov, dict) and hasattr(ov, "mime_type") and ov.mime_type:
            mime_type = ov.mime_type
        elif isinstance(ov, dict) and ov.get("mime_type"):
            mime_type = ov.get("mime_type")

        clean_name = "".join(c if c.isalnum() else "_" for c in dish_name.lower())
        filename = f"{clean_name}_{uuid.uuid4().hex[:6]}.mp4"

        # (1) Save artifact for Playground
        artifact_part = types.Part.from_bytes(data=vbytes, mime_type=mime_type)
        tool_context.save_artifact(filename=filename, artifact=artifact_part)

        # (2) Upload to public Cloud Storage bucket
        storage_client = storage.Client(project=PROJECT_ID)
        bucket = storage_client.bucket(BUCKET_NAME)
        blob = bucket.blob(filename)
        blob.upload_from_string(vbytes, content_type=mime_type)

        return f"https://storage.googleapis.com/{BUCKET_NAME}/{filename}"
    except Exception as e:
        return f"Error generating recipe video: {str(e)}"


def lookup_global_recipes(query: str) -> str:
    """Searches the public TheMealDB online database for global recipes by dish or main ingredient name.

    Args:
        query: Search term for the recipe or main ingredient (e.g. 'curry', 'tacos', 'pasta', 'chicken').

    Returns:
        A formatted list of matching online recipes with category, cuisine, ingredients, and instructions.
    """
    api_key = os.environ.get("THEMEALDB_API_KEY", "1")
    url = f"https://www.themealdb.com/api/json/v1/{api_key}/search.php?s={urllib.parse.quote(query)}"

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "RecipeAssistantAgent/1.0"})
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())

        meals = data.get("meals")
        if not meals:
            return f"No global recipes found on TheMealDB matching '{query}'."

        results = []
        for m in meals[:3]:  # Top 3 matching dishes
            ingredients = []
            for i in range(1, 21):
                ing = m.get(f"strIngredient{i}")
                measure = m.get(f"strMeasure{i}")
                if ing and ing.strip():
                    measure_str = f" ({measure.strip()})" if measure and measure.strip() else ""
                    ingredients.append(f"{ing.strip()}{measure_str}")

            instructions = m.get("strInstructions", "").replace("\r\n", " ")
            if len(instructions) > 300:
                instructions = instructions[:300] + "..."

            results.append(
                f"Title: {m.get('strMeal')}\n"
                f"Category/Cuisine: {m.get('strCategory')} / {m.get('strArea')}\n"
                f"Ingredients: {', '.join(ingredients)}\n"
                f"Instructions: {instructions}"
            )

        return "\n\n---\n\n".join(results)
    except Exception as e:
        return f"Error querying TheMealDB API: {str(e)}"


def search_recipes(cuisine: str = "", ingredient: str = "", max_prep_time: int = 0) -> str:
    """Searches the Firestore recipes collection based on criteria like cuisine, ingredient, or maximum prep time.

    Args:
        cuisine: Optional cuisine filter (e.g. 'Italian', 'Asian').
        ingredient: Optional ingredient filter (e.g. 'garlic', 'chicken', 'tomatoes').
        max_prep_time: Optional maximum prep time in minutes (e.g. 30).

    Returns:
        A formatted string of matching recipes with title, cuisine, prep time, ingredients, and ID.
    """
    db = get_firestore_client()
    recipes_ref = db.collection("recipes")
    docs = recipes_ref.stream()

    matches = []
    for doc in docs:
        data = doc.to_dict()
        data["id"] = doc.id

        if cuisine and cuisine.lower() not in data.get("cuisine", "").lower():
            continue
        if ingredient and not any(ingredient.lower() in ing.lower() for ing in data.get("ingredients", [])):
            continue
        if max_prep_time > 0 and data.get("prep_time_minutes", 0) > max_prep_time:
            continue

        matches.append(data)

    if not matches:
        return f"No recipes found matching criteria (cuisine='{cuisine}', ingredient='{ingredient}', max_prep_time={max_prep_time})."

    results = []
    for m in matches:
        gf = " [Gluten-Free]" if m.get("is_gluten_free") else ""
        peanuts = " ⚠️ Contains Peanuts" if m.get("contains_peanuts") else ""
        results.append(
            f"ID: {m['id']} | Title: {m.get('title')}{gf}{peanuts}\n"
            f"  Cuisine: {m.get('cuisine')} | Prep Time: {m.get('prep_time_minutes')} mins\n"
            f"  Ingredients: {', '.join(m.get('ingredients', []))}\n"
            f"  Instructions: {m.get('instructions')}"
        )

    return "\n\n".join(results)


def add_recipe(
    title: str,
    ingredients: list[str],
    cuisine: str,
    prep_time_minutes: int,
    instructions: str,
    is_gluten_free: bool = False,
    contains_peanuts: bool = False,
) -> str:
    """Adds a new recipe document to the Firestore recipes database.

    Args:
        title: The title of the recipe (e.g., 'Garlic Butter Salmon').
        ingredients: A list of ingredients needed (e.g., ['salmon fillet', 'butter', 'garlic', 'lemon']).
        cuisine: The cuisine style (e.g., 'Seafood', 'Italian', 'Asian').
        prep_time_minutes: Preparation and cooking time in minutes.
        instructions: Step-by-step cooking instructions.
        is_gluten_free: Whether the recipe is gluten-free.
        contains_peanuts: Whether the recipe contains peanuts or peanut products.

    Returns:
        A confirmation message with the generated recipe ID.
    """
    db = get_firestore_client()
    doc_id = title.lower().replace(" ", "-").replace("'", "")
    doc_ref = db.collection("recipes").document(doc_id)

    recipe_data = {
        "id": doc_id,
        "title": title,
        "cuisine": cuisine,
        "ingredients": ingredients,
        "prep_time_minutes": prep_time_minutes,
        "instructions": instructions,
        "is_gluten_free": is_gluten_free,
        "contains_peanuts": contains_peanuts,
    }

    doc_ref.set(recipe_data)
    return f"Successfully added recipe '{title}' to Firestore with ID '{doc_id}'."


def get_recipe_details(recipe_id: str) -> str:
    """Fetches full details for a specific recipe from Firestore by recipe ID.

    Args:
        recipe_id: The document ID of the recipe in Firestore (e.g., 'spaghetti-margherita').

    Returns:
        The detailed recipe information or an error message if not found.
    """
    db = get_firestore_client()
    doc_ref = db.collection("recipes").document(recipe_id)
    doc = doc_ref.get()

    if not doc.exists:
        return f"Recipe with ID '{recipe_id}' was not found in Firestore."

    data = doc.to_dict()
    gf = "Yes" if data.get("is_gluten_free") else "No"
    peanuts = "Yes" if data.get("contains_peanuts") else "No"

    return (
        f"Title: {data.get('title')}\n"
        f"ID: {doc.id}\n"
        f"Cuisine: {data.get('cuisine')}\n"
        f"Prep Time: {data.get('prep_time_minutes')} minutes\n"
        f"Gluten-Free: {gf}\n"
        f"Contains Peanuts: {peanuts}\n"
        f"Ingredients:\n- " + "\n- ".join(data.get("ingredients", [])) + "\n"
        f"Instructions:\n{data.get('instructions')}"
    )


def add_to_grocery_list(items: list[str]) -> str:
    """Appends items to the user's grocery list in Firestore.

    Args:
        items: A list of ingredient or item names to add to the grocery list (e.g. ['parmesan cheese', 'fresh basil']).

    Returns:
        A confirmation message with the updated grocery list.
    """
    db = get_firestore_client()
    doc_ref = db.collection("grocery_list").document("user_groceries")
    doc = doc_ref.get()

    existing_items = []
    if doc.exists:
        existing_items = doc.to_dict().get("items", [])

    new_items = list(dict.fromkeys(existing_items + items))
    doc_ref.set({"items": new_items, "updated_at": firestore.SERVER_TIMESTAMP})

    return f"Successfully added {len(items)} item(s) to your grocery list. Current grocery list: {', '.join(new_items)}"


def get_grocery_list() -> str:
    """Retrieves the user's current grocery shopping list from Firestore.

    Returns:
        The current list of grocery items or a message if empty.
    """
    db = get_firestore_client()
    doc_ref = db.collection("grocery_list").document("user_groceries")
    doc = doc_ref.get()

    if not doc.exists or not doc.to_dict().get("items"):
        return "Your grocery list is currently empty."

    items = doc.to_dict().get("items", [])
    return "Current Grocery List:\n- " + "\n- ".join(items)


def geocode_address(address: str) -> str:
    """Converts a street address or city name into geographical coordinates using Google Maps Geocoding API.

    Args:
        address: The street address, city, or location query (e.g. '1600 Amphitheatre Pkwy, Mountain View, CA').

    Returns:
        The formatted address, latitude, and longitude.
    """
    maps_key = os.environ.get("GOOGLE_MAPS_API_KEY", "")
    if not maps_key:
        return "Error: GOOGLE_MAPS_API_KEY environment variable is not set."

    url = f"https://maps.googleapis.com/maps/api/geocode/json?address={urllib.parse.quote(address)}&key={maps_key}"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())

        if data.get("status") != "OK" or not data.get("results"):
            return f"Geocoding failed for address '{address}': {data.get('status')}"

        result = data["results"][0]
        loc = result["geometry"]["location"]
        return (
            f"Formatted Address: {result.get('formatted_address')}\n"
            f"Latitude: {loc.get('lat')}\n"
            f"Longitude: {loc.get('lng')}"
        )
    except Exception as e:
        return f"Error during geocoding: {str(e)}"


def find_nearby_places(latitude: float, longitude: float, place_type: str = "supermarket", radius_meters: float = 3000.0) -> str:
    """Finds nearby places of a given type around a latitude/longitude coordinate using Google Places API (New).

    Args:
        latitude: Latitude of the center location.
        longitude: Longitude of the center location.
        place_type: The place type filter (e.g. 'supermarket', 'bakery', 'restaurant', 'convenience_store').
        radius_meters: Radius to search in meters (default 3000.0).

    Returns:
        A list of nearby places with name, formatted address, and location coordinates.
    """
    maps_key = os.environ.get("GOOGLE_MAPS_API_KEY", "")
    if not maps_key:
        return "Error: GOOGLE_MAPS_API_KEY environment variable is not set."

    url = "https://places.googleapis.com/v1/places:searchNearby"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": maps_key,
        "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.location",
    }
    body = {
        "includedTypes": [place_type],
        "locationRestriction": {
            "circle": {
                "center": {"latitude": latitude, "longitude": longitude},
                "radius": radius_meters,
            }
        },
    }

    try:
        req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())

        places = data.get("places", [])
        if not places:
            return f"No nearby places of type '{place_type}' found within {radius_meters}m radius."

        results = []
        for p in places[:5]:  # Top 5 nearby places
            name = p.get("displayName", {}).get("text", "N/A")
            addr = p.get("formattedAddress", "N/A")
            loc = p.get("location", {})
            results.append(
                f"Name: {name}\n"
                f"Address: {addr}\n"
                f"Location: ({loc.get('latitude')}, {loc.get('longitude')})"
            )

        return "\n\n---\n\n".join(results)
    except Exception as e:
        return f"Error querying Places API (New): {str(e)}"


def get_weather(query: str) -> str:
    """Simulates a web search. Use it get information on weather.

    Args:
        query: A string containing the location to get weather information for.

    Returns:
        A string with the simulated weather information for the queried location.
    """
    if "sf" in query.lower() or "san francisco" in query.lower():
        return "It's 60 degrees and foggy."
    return "It's 90 degrees and sunny."


def get_current_time(query: str) -> str:
    """Simulates getting the current time for a city.

    Args:
        city: The name of the city to get the current time for.

    Returns:
        A string with the current time information.
    """
    if "sf" in query.lower() or "san francisco" in query.lower():
        tz_identifier = "America/Los_Angeles"
    else:
        return f"Sorry, I don't have timezone information for query: {query}."

    tz = ZoneInfo(tz_identifier)
    now = datetime.datetime.now(tz)
    return f"The current time for query {query} is {now.strftime('%Y-%m-%d %H:%M:%S %Z%z')}"


async def generate_memories_callback(callback_context: CallbackContext):
    """WRITE: After each agent turn, extract and save session facts into Memory Bank."""
    await callback_context.add_session_to_memory()
    return None


root_agent = Agent(
    name="root_agent",
    model=Gemini(
        model="gemini-flash-latest",
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=a2ui_instruction,
    tools=[
        PreloadMemoryTool(),
        search_recipes,
        add_recipe,
        get_recipe_details,
        add_to_grocery_list,
        get_grocery_list,
        lookup_global_recipes,
        geocode_address,
        find_nearby_places,
        generate_dish_image,
        generate_recipe_video,
        get_weather,
        get_current_time,
    ],
    code_executor=code_executor,
    after_agent_callback=generate_memories_callback,
    after_model_callback=a2ui_callback,
)

app = App(
    root_agent=root_agent,
    name="app",
)
