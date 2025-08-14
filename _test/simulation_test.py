# simulation_test.py

import asyncio
import httpx
import random
import time
from typing import List, Dict, Any, Optional

# --- Configuration ---
BASE_URL = "http://localhost:8000"
NUM_USERS = 25  # Number of concurrent users to simulate
SIMULATION_DURATION_SECONDS = 180  # How long to run the simulation (in seconds)
DEFAULT_PASSWORD = "password123"

# --- Helper Functions ---
def log(message: str):
    """Simple logger with a timestamp."""
    print(f"[{time.strftime('%H:%M:%S')}] {message}")

# --- API Client Class ---
class ApiClient:
    """A wrapper for httpx.AsyncClient to handle API calls and authentication."""
    def __init__(self, base_url: str):
        self._client = httpx.AsyncClient(base_url=base_url, timeout=20.0)
        self.token: Optional[str] = None

    async def close(self):
        await self._client.aclose()

    @property
    def headers(self) -> Dict[str, str]:
        """Returns headers for authenticated requests."""
        if not self.token:
            return {}
        return {"Authorization": f"Bearer {self.token}"}

    async def login(self, username: str, password: str) -> bool:
        """Login and store the auth token."""
        try:
            response = await self._client.post(
                "/api/users/login",
                data={"username": username, "password": password}
            )
            response.raise_for_status()
            self.token = response.json()["access_token"]
            return True
        except httpx.HTTPStatusError as e:
            log(f"ERROR logging in {username}: {e.response.status_code} - {e.response.text}")
            self.token = None
            return False

    async def get(self, endpoint: str) -> Optional[Any]:
        """Perform an authenticated GET request."""
        try:
            response = await self._client.get(endpoint, headers=self.headers)
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPStatusError, httpx.RequestError) as e:
            log(f"ERROR on GET {endpoint}: {e}")
            return None

    async def post(self, endpoint: str, json_data: Dict = None) -> Optional[Any]:
        """Perform an authenticated POST request."""
        try:
            response = await self._client.post(endpoint, json=json_data, headers=self.headers)
            response.raise_for_status()
            # Handle empty response bodies often returned on success
            if response.status_code in [201, 204] and not response.content:
                return {"status": "success", "code": response.status_code}
            return response.json()
        except httpx.HTTPStatusError as e:
            # Don't log 429 (Too Many Requests) or 409 (Conflict) as errors, they are expected
            if e.response.status_code not in [429, 409, 402]:
                log(f"ERROR on POST {endpoint}: {e.response.status_code} - {e.response.text}")
            return None
        except httpx.RequestError as e:
            log(f"REQUEST ERROR on POST {endpoint}: {e}")
            return None

# --- Agent Class ---
class Agent:
    """Represents a simulated user, performing actions through an ApiClient."""
    def __init__(self, username: str, password: str):
        self.username = username
        self.password = password
        self.client = ApiClient(BASE_URL)
        self.state: Dict[str, Any] = {}
        self.level_status: Dict[str, Any] = {}
        self.is_active = True

    async def life_cycle(self):
        """The main loop for an agent, simulating continuous user activity."""
        log(f"Agent {self.username} starting life cycle.")
        if not await self.client.login(self.username, self.password):
            log(f"Agent {self.username} failed initial login. Shutting down.")
            return

        start_time = time.time()
        while time.time() - start_time < SIMULATION_DURATION_SECONDS:
            if not self.is_active: break
            
            log(f"Agent {self.username} starting a new round of actions.")
            await self.update_state()
            if not self.state:
                log(f"Agent {self.username} could not fetch state. Shutting down.")
                break

            # Perform actions concurrently to simulate a user doing multiple things
            await asyncio.gather(
                self.do_tasks(),
                self.consider_shopping(),
                self.consider_land_management(),
                self.consider_level_upgrade()
            )

            idle_time = random.uniform(8, 20)
            log(f"Agent {self.username} is idling for {idle_time:.1f} seconds.")
            await asyncio.sleep(idle_time)
        
        log(f"Agent {self.username} finished life cycle.")
        await self.client.close()

    async def update_state(self):
        """Fetches the latest user and level status from the server."""
        me_data = await self.client.get("/api/users/me")
        if me_data:
            self.state = me_data
            log(f"Agent {self.username}: State updated. Balance: {self.state.get('hc_balance', 'N/A')}, Level: {self.state.get('level', 'N/A')}")
        
        level_status_data = await self.client.get("/api/hustles/level-status")
        if level_status_data:
            self.level_status = level_status_data

    async def do_tasks(self):
        """Simulates completing various tasks."""
        if random.random() < 0.8:  # 80% chance to do quick taps
             for _ in range(random.randint(5, 20)):
                await self.client.post("/api/tasks/complete", {"task_id": "quick_tap"})
                await asyncio.sleep(0.1)
             log(f"Agent {self.username} did some quick tapping.")

        await self.attempt_task("daily_check_in")
        await self.attempt_task("watch_ad")
        await self.attempt_quiz_task()

    async def attempt_task(self, task_id: str):
        """Generic task completion attempt."""
        result = await self.client.post("/api/tasks/complete", {"task_id": task_id})
        if result and result.get("new_balance"):
            log(f"Agent {self.username} completed task '{task_id}'. New balance: {result.get('new_balance')}")

    async def attempt_quiz_task(self):
        """Fetches a quiz and attempts to answer it."""
        quiz_question = await self.client.get("/api/tasks/quiz/fetch")
        if not quiz_question: return

        num_options = len(quiz_question.get('options', []))
        if num_options == 0: return
            
        chosen_answer_index = random.randint(0, num_options - 1)
        
        payload = {"task_id": "quiz_game", "payload": {"quizId": quiz_question["quizId"], "answerIndex": chosen_answer_index}}
        
        result = await self.client.post("/api/tasks/complete", payload)
        if result:
            log(f"Agent {self.username} answered quiz. Result: Correct! New balance: {result.get('new_balance')}")
        else:
            log(f"Agent {self.username} answered quiz. Result: Incorrect or on cooldown.")

    async def consider_shopping(self):
        """Decides whether to buy an item from the shop."""
        if not self.state or random.random() > 0.2: return
        
        items = await self.client.get("/api/shop/items")
        if not items: return
        
        affordable_items = [item for item in items if item['price'] <= self.state.get('hc_balance', 0) and item['item_type'] != "BUNDLE"]
        if not affordable_items: return

        item_to_buy = random.choice(affordable_items)
        log(f"Agent {self.username} is attempting to buy '{item_to_buy['name']}' for {item_to_buy['price']} HC.")
        result = await self.client.post("/api/shop/purchase", {"item_id": item_to_buy['item_id']})
        if result:
            log(f"Agent {self.username} successfully bought '{item_to_buy['name']}'.")
            await self.update_state()

    async def consider_land_management(self):
        """Decides whether to buy or sell land."""
        if not self.state: return
        
        if random.random() < 0.1 and self.state.get('hc_balance', 0) > 500:
            import h3
            res = 10 # must match server config
            lat, lon = random.uniform(-23.6, -23.5), random.uniform(-46.7, -46.6) # Sao Paulo area
            h3_index = h3.latlng_to_cell(lat, lon, res)

            log(f"Agent {self.username} attempting to buy land tile {h3_index}.")
            result = await self.client.post(f"/api/land/buy/{h3_index}")
            if result:
                log(f"Agent {self.username} successfully bought land {h3_index}.")
                await self.update_state()
        elif random.random() < 0.05:
            my_lands = await self.client.get("/api/land/my-lands")
            if my_lands:
                land_to_sell = random.choice(my_lands)
                h3_index = land_to_sell['h3_index']
                log(f"Agent {self.username} attempting to sell land tile {h3_index}.")
                result = await self.client.post(f"/api/land/sell/{h3_index}")
                if result:
                    log(f"Agent {self.username} successfully sold land {h3_index}.")
                    await self.update_state()

    async def consider_level_upgrade(self):
        """Checks for upgrade eligibility and performs it if possible."""
        if not self.level_status or not self.level_status.get('is_eligible_for_upgrade'):
            return

        log(f"!!! Agent {self.username} is ELIGIBLE FOR LEVEL UPGRADE! Attempting to upgrade. !!!")
        upgrade_result = await self.client.post("/api/hustles/level-upgrade")
        if not upgrade_result:
            log(f"Agent {self.username} level upgrade failed unexpectedly.")
            return

        log(f"SUCCESS! Agent {self.username} upgraded to level {upgrade_result.get('new_level')}!")
        await self.update_state()

        available_hustles = await self.client.get("/api/hustles/available")
        if available_hustles:
            new_hustle = random.choice(available_hustles)
            log(f"Agent {self.username} is selecting a new hustle: '{new_hustle}'")
            await self.client.post("/api/hustles/select", {"hustle_name": new_hustle})
        else:
            log(f"Agent {self.username} is at max level or no hustles found after upgrade.")

# --- Main Simulation Orchestrator ---
class Simulation:
    def __init__(self):
        self.client = ApiClient(BASE_URL)

    async def setup(self) -> List[Agent]:
        """Resets DB, seeds data, and prepares agents."""
        log("--- STARTING SIMULATION SETUP ---")
        
        log("1. Resetting database...")
        await self.client.post("/api/dev/reset-database")

        log("2. Seeding quiz data...")
        quiz_data = {
            "quizzes": [
                {"question_pt": "Qual é a capital de Angola?", "question_en": "What is the capital of Angola?", "options_pt": ["Huambo", "Luanda", "Benguela"], "options_en": ["Huambo", "Luanda", "Benguela"], "correctAnswerIndex": 1},
                {"question_pt": "Qual cor se obtém misturando amarelo e azul?", "question_en": "What color do you get by mixing yellow and blue?", "options_pt": ["Vermelho", "Laranja", "Verde"], "options_en": ["Red", "Orange", "Green"], "correctAnswerIndex": 2},
                {"question_pt": "Quantos dias tem um ano bissexto?", "question_en": "How many days are in a leap year?", "options_pt": ["365", "366", "364"], "options_en": ["365", "366", "364"], "correctAnswerIndex": 1}
            ]
        }
        await self.client.post("/api/dev/seed-quiz", quiz_data)

        log(f"3. Seeding {NUM_USERS} users with starting cash...")
        seed_payload = {"count": NUM_USERS, "give_coins": 2500}
        seed_result = await self.client.post("/api/dev/seed-users", seed_payload)
        
        if not seed_result or "users" not in seed_result:
            log("FATAL: Seeding users failed. Aborting.")
            return []
            
        agents = [Agent(user['username'], DEFAULT_PASSWORD) for user in seed_result['users']]
        log("--- SIMULATION SETUP COMPLETE ---")
        return agents

    async def run(self):
        """Runs the full simulation."""
        agents = await self.setup()
        if not agents:
            await self.client.close()
            return

        log(f"--- STARTING SIMULATION RUN ({NUM_USERS} users for {SIMULATION_DURATION_SECONDS}s) ---")
        tasks = [agent.life_cycle() for agent in agents]
        await asyncio.gather(*tasks)

        log("--- SIMULATION RUN COMPLETE ---")
        await self.report()
        await self.client.close()

    async def report(self):
        """Prints a final report of the simulation."""
        log("\n--- FINAL SIMULATION REPORT ---")
        leaderboard = await self.client.get("/api/leaderboard")
        if leaderboard:
            log("\n--- Top 10 Leaderboard ---")
            for i, user in enumerate(leaderboard):
                log(f"{i+1: >2}. {user['username']:<20} | Level: {user['level']:<3} | Balance: {user['hc_balance']}")
            log("--------------------------\n")
        else:
            log("Could not fetch leaderboard.")

if __name__ == "__main__":
    # Check for required libraries
    try:
        import h3
        from faker import Faker
    except ImportError as e:
        print(f"Error: Missing required library '{e.name}'.")
        print("Please install the required libraries: pip install httpx faker h3")
        exit(1)

    sim = Simulation()
    try:
        asyncio.run(sim.run())
    except httpx.ConnectError:
        log("\nFATAL: Connection could not be established.")
        log("Is the server running? Start it with: uvicorn app:app --reload")