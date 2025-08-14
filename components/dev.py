# components/dev.py

from datetime import datetime
import html
import json
import random
from faker import Faker
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import List

# Import all Beanie models to be managed
from .users import User, get_password_hash
from .tasks import Quiz
from .land import LandTile
from .hustles import HUSTLE_CONFIG

router = APIRouter(prefix="/api/dev", tags=["Developer"])
fake = Faker()

@router.post("/reset-database")
async def reset_database():
    """
    Deletes all data from users, quizzes, and land_tiles collections.
    USE WITH CAUTION.
    """
    await User.delete_all()
    await Quiz.delete_all()
    await LandTile.delete_all()
    return {"message": "Database has been reset. All user, quiz, and land data wiped."}


class UserSeedPayload(BaseModel):
    count: int = 20
    give_coins: int = 2000 # Give some starting coins for testing shop and land features.

@router.post("/seed-users")
async def seed_users(payload: UserSeedPayload):
    """
    Creates a specified number of dummy users with a standard password ("password123").
    """
    created_users = []
    level_1_hustles = HUSTLE_CONFIG.get(1, [])
    if not level_1_hustles:
         raise HTTPException(status_code=500, detail="No level 1 hustles are configured in hustles.py.")

    for i in range(payload.count):
        # Generate a unique username and email
        username = fake.user_name() + str(random.randint(100, 999))
        email = f"{username}@example.com"
        
        # In the unlikely event of a collision, skip and try the next one
        if await User.find_one(User.username == username) or await User.find_one(User.email == email):
            continue

        # Use a standard, easy-to-remember password for all test users
        hashed_password = get_password_hash("password123")
        
        user = User(
            username=username,
            email=email,
            hashed_password=hashed_password,
            hc_balance=payload.give_coins,
            level=1, # All users start at level 1
            current_hustle=random.choice(level_1_hustles),
            language=random.choice(['en', 'pt'])
        )
        await user.create()
        created_users.append({"username": user.username, "email": user.email})

    return {
        "message": f"Successfully created {len(created_users)} dummy users.",
        "password_for_all": "password123",
        "users": created_users
    }


















# --- DTOs for Quiz Seeding ---
class QuizSeedItem(BaseModel):
    """Represents a single quiz question to be seeded."""
    question_pt: str
    question_en: str
    options_pt: List[str]
    options_en: List[str]
    correctAnswerIndex: int

class QuizSeedPayload(BaseModel):
    """The payload for the seed-quiz endpoint, containing a list of quizzes."""
    quizzes: List[QuizSeedItem]


@router.post("/seed-quiz")
async def seed_quiz_data(payload: QuizSeedPayload):
    """
    Endpoint to add multiple quizzes to the DB from a dictionary payload.
    It checks for duplicate questions (based on 'question_en') and skips them.
    Not for production use.
    """
    added_count = 0
    skipped_count = 0

    for quiz_data in payload.quizzes:
        # Check if a quiz with the same English question already exists
        existing_quiz = await Quiz.find_one({"question_en": quiz_data.question_en})

        if existing_quiz:
            skipped_count += 1
            continue  # Skip to the next item if a duplicate is found
        
        # If no duplicate, create and insert the new quiz
        new_quiz = Quiz(
            **quiz_data.model_dump(),
            isActive=True  # Ensure all seeded quizzes are active
        )
        await new_quiz.create()
        added_count += 1

    return {
        "message": "Quiz seeding process completed.",
        "quizzes_added": added_count,
        "duplicates_skipped": skipped_count
    }















































































# ==============================================================================
# UPGRADED INTERACTIVE DATABASE VIEWER
# ==============================================================================

def format_value_for_html(value):
    """Helper function to format values for the initial, non-expanded HTML display."""
    if value is None:
        return "<em>None</em>"
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, list) or isinstance(value, dict):
        # For complex types, show a summary and let the user expand for details
        count = len(value)
        item_type = "item" if isinstance(value, list) else "key"
        s = 's' if count != 1 else ''
        return f"<em>({count} {item_type}{s})</em>"
    
    # Shorten long strings
    str_val = str(value)
    if len(str_val) > 40:
        return f"<span title='{html.escape(str_val)}'>{html.escape(str_val[:30])}...</span>"
        
    return html.escape(str_val)

def generate_interactive_table(title: str, documents: list, table_id: str) -> str:
    """Generates an interactive HTML table with expandable rows."""
    if not documents:
        return f"<h2>{title}</h2><p>No documents found in this collection.</p>"

    headers = sorted(list(set(key for doc in documents for key in doc.keys())))
    
    table_html = f"<h2>{title} ({len(documents)} records)</h2>"
    table_html += f"<table id='{table_id}'>"
    
    # Header
    table_html += "<thead><tr>"
    for header in headers:
        table_html += f"<th>{html.escape(header)}</th>"
    table_html += "</tr></thead>"
    
    # Body
    table_html += "<tbody>"
    for i, doc in enumerate(documents):
        # Store full, unformatted data in a data-* attribute for JS
        full_data_json = html.escape(json.dumps(doc, default=str))
        table_html += f"<tr class='data-row' data-details='{full_data_json}'>"
        for header in headers:
            table_html += f"<td>{format_value_for_html(doc.get(header))}</td>"
        table_html += "</tr>"
    table_html += "</tbody></table>"
    
    return table_html

@router.get("/db-viewer", response_class=HTMLResponse)
async def get_database_viewer_interactive():
    """
    Provides an INTERACTIVE HTML view of the database with tabs and expandable rows.
    """
    # Fetch all data
    users = await User.find_all(sort=[("hc_balance", -1)]).to_list() # Sort users by balance
    land_tiles = await LandTile.find_all().to_list()
    quizzes = await Quiz.find_all().to_list()
    
    user_docs = [user.model_dump() for user in users]
    land_tile_docs = [tile.model_dump() for tile in land_tiles]
    quiz_docs = [quiz.model_dump() for quiz in quizzes]

    # Generate HTML for each table
    users_table = generate_interactive_table("Users", user_docs, "users-table")
    land_table = generate_interactive_table("Land Tiles", land_tile_docs, "land-table")
    quiz_table = generate_interactive_table("Quizzes", quiz_docs, "quiz-table")

    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>HustleCoin DB Viewer</title>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; line-height: 1.6; background-color: #f4f4f9; color: #333; margin: 0; padding: 0; }}
            .container {{ max-width: 95%; margin: 20px auto; padding: 20px; background: #fff; border-radius: 8px; box-shadow: 0 0 15px rgba(0,0,0,0.1); }}
            h1 {{ color: #1a1a1a; text-align: center; border-bottom: 2px solid #ddd; padding-bottom: 10px; }}
            h2 {{ color: #333; border-bottom: 1px solid #eee; padding-bottom: 5px; margin-top: 40px; }}
            .tab-container {{ display: flex; border-bottom: 2px solid #ccc; margin-bottom: 20px; }}
            .tab {{ padding: 10px 20px; cursor: pointer; background-color: #e9e9e9; border: 1px solid #ccc; border-bottom: none; margin-bottom: -2px; border-radius: 5px 5px 0 0; }}
            .tab.active {{ background-color: #fff; border-bottom: 2px solid #fff; }}
            .tab-content {{ display: none; }}
            .tab-content.active {{ display: block; }}
            table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
            th, td {{ padding: 10px 12px; text-align: left; border: 1px solid #ddd; word-wrap: break-word; }}
            thead tr {{ background-color: #4CAF50; color: white; }}
            tbody tr.data-row {{ cursor: pointer; }}
            tbody tr.data-row:nth-of-type(even) {{ background-color: #f9f9f9; }}
            tbody tr.data-row:hover {{ background-color: #e8f4f8; }}
            tr.details-row {{ background-color: #fdfde2 !important; }}
            tr.details-row td {{ padding: 0; }}
            .details-content {{ padding: 15px; background: #fff9c4; }}
            .details-content pre {{ white-space: pre-wrap; word-wrap: break-word; background: #2d2d2d; color: #f8f8f2; padding: 15px; border-radius: 5px; margin: 0; }}
            em {{ color: #888; }}
            span[title] {{ cursor: help; border-bottom: 1px dotted #888; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>HustleCoin Interactive DB Viewer</h1>
            
            <div class="tab-container">
                <div class="tab active" onclick="showTab('users')">Users</div>
                <div class="tab" onclick="showTab('land')">Land Tiles</div>
                <div class="tab" onclick="showTab('quizzes')">Quizzes</div>
            </div>

            <div id="users" class="tab-content active">{users_table}</div>
            <div id="land" class="tab-content">{land_table}</div>
            <div id="quizzes" class="tab-content">{quiz_table}</div>
        </div>

        <script>
            function showTab(tabName) {{
                // Handle tab content visibility
                document.querySelectorAll('.tab-content').forEach(tab => tab.classList.remove('active'));
                document.getElementById(tabName).classList.add('active');
                
                // Handle tab button active state
                document.querySelectorAll('.tab').forEach(tab => tab.classList.remove('active'));
                event.currentTarget.classList.add('active');
            }}

            document.querySelectorAll('.data-row').forEach(row => {{
                row.addEventListener('click', function() {{
                    // Remove any existing details row
                    const existingDetailRow = this.parentNode.querySelector('.details-row');
                    if (existingDetailRow) {{
                        const wasMyDetail = existingDetailRow.previousElementSibling === this;
                        existingDetailRow.remove();
                        // If it was my detail row, I'm done.
                        if (wasMyDetail) return;
                    }}
                    
                    const detailsJson = this.getAttribute('data-details');
                    const detailsObj = JSON.parse(detailsJson);
                    
                    // Create a new row for details
                    const detailRow = this.parentNode.insertRow(this.rowIndex);
                    detailRow.classList.add('details-row');
                    
                    const cell = detailRow.insertCell(0);
                    cell.colSpan = this.cells.length; // Span across all columns
                    
                    // Pretty-print the JSON inside a <pre> tag
                    const pre = document.createElement('pre');
                    pre.textContent = JSON.stringify(detailsObj, null, 2);
                    
                    const contentDiv = document.createElement('div');
                    contentDiv.className = 'details-content';
                    contentDiv.appendChild(pre);
                    cell.appendChild(contentDiv);
                }});
            }});
        </script>
    </body>
    </html>
    """
    
    return HTMLResponse(content=html_content)