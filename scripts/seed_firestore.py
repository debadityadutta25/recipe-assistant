# Copyright 2026 Google LLC
"""Script to seed initial recipe items into Firestore."""

import time
from google.cloud import firestore

# CRITICAL: Hardcoded project ID as string per Agent Platform requirements
PROJECT_ID = "qwiklabs-gcp-03-2b2a39607757"


def seed_recipes():
    print(f"Connecting to Firestore with project_id={PROJECT_ID}...")
    db = firestore.Client(project=PROJECT_ID)
    recipes_ref = db.collection("recipes")

    recipes = [
        {
            "id": "spaghetti-margherita",
            "title": "Classic Spaghetti Margherita",
            "cuisine": "Italian",
            "ingredients": ["spaghetti", "tomatoes", "fresh basil", "extra virgin olive oil", "garlic", "parmesan cheese"],
            "prep_time_minutes": 20,
            "instructions": "Boil spaghetti in salted water. Sauté garlic and tomatoes in olive oil. Toss pasta with sauce and fresh basil. Top with grated parmesan.",
            "is_gluten_free": False,
            "contains_peanuts": False,
        },
        {
            "id": "penne-arrabbiata-gf",
            "title": "Gluten-Free Penne Arrabbiata",
            "cuisine": "Italian",
            "ingredients": ["gluten-free penne", "crushed tomatoes", "red chili flakes", "garlic", "olive oil", "parsley"],
            "prep_time_minutes": 25,
            "instructions": "Cook gluten-free penne. Heat olive oil, add minced garlic and chili flakes. Add crushed tomatoes and simmer. Toss pasta with sauce.",
            "is_gluten_free": True,
            "contains_peanuts": False,
        },
        {
            "id": "chicken-broccoli-stirfry",
            "title": "Chicken Broccoli Stir-Fry",
            "cuisine": "Asian",
            "ingredients": ["chicken breast", "broccoli florets", "soy sauce", "garlic", "ginger", "sesame oil", "cornstarch"],
            "prep_time_minutes": 25,
            "instructions": "Stir-fry chicken strips until browned. Add broccoli, garlic, and ginger. Stir in soy sauce and sesame oil. Simmer until sauce thickens.",
            "is_gluten_free": True,
            "contains_peanuts": False,
        },
        {
            "id": "tuscan-garlic-chicken",
            "title": "Creamy Tuscan Garlic Chicken",
            "cuisine": "Italian",
            "ingredients": ["chicken thighs", "sun-dried tomatoes", "spinach", "heavy cream", "garlic", "olive oil"],
            "prep_time_minutes": 30,
            "instructions": "Sear chicken thighs until golden. Remove chicken and sauté garlic, sun-dried tomatoes, and spinach. Add heavy cream, return chicken, and simmer.",
            "is_gluten_free": True,
            "contains_peanuts": False,
        },
    ]

    for item in recipes:
        doc_ref = recipes_ref.document(item["id"])
        for attempt in range(5):
            try:
                doc_ref.set(item)
                print(f"Seeded recipe: {item['title']} ({item['id']})")
                break
            except Exception as e:
                print(f"Attempt {attempt+1} failed for {item['id']}: {e}. Retrying in 1s...")
                time.sleep(1)

    print("Firestore seeding complete!")


if __name__ == "__main__":
    seed_recipes()
