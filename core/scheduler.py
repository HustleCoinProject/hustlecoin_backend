import asyncio

from core.game_logic import distribute_land_income_logic_stateful

# Define the interval in seconds.
# 43200 seconds = 12 hours
# 86400 seconds = 24 hours
INCOME_DISTRIBUTION_INTERVAL_SECONDS = 43200 

async def periodic_land_income_task():
    """
    A background task that runs forever, distributing land income at a fixed interval.
    """
    print("Periodic land income task has started.")
    while True:
        try:
            # Wait for the specified interval.
            # We put the sleep at the beginning to wait for the first interval before running.
            await asyncio.sleep(INCOME_DISTRIBUTION_INTERVAL_SECONDS)
            
            # Run the actual income distribution logic.
            await distribute_land_income_logic_stateful()
            
        except Exception as e:
            # This is a critical safety net. If anything goes wrong during the
            # income distribution (e.g., database connection issue), we log the
            # error but don't crash the background task. The loop will continue.
            print(f"An error occurred in the periodic land income task: {e}")
            # Optional: Add more robust logging or alert system here.
            # We might want a shorter sleep after an error to retry sooner.
            await asyncio.sleep(60) # Wait 1 minute before trying again after an error.