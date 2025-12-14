# components/tasks.py
from datetime import datetime, timedelta, date
from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Request
from core.rate_limiter_slowapi import api_limiter
from pydantic import BaseModel, Field
from beanie import PydanticObjectId
from beanie.operators import Inc, Set
import random

from data.models import User, Quiz
from core.security import get_current_user, get_current_verified_user
from core.game_logic import GameLogic
from core.cache import SimpleCache

router = APIRouter(prefix="/api/tasks", tags=["Tasks & Quizzes"])

# Cache for quiz list (30 minutes)
quiz_cache = SimpleCache[List[Quiz]](ttl_seconds=1800)

# --- Task Configuration ---
# This dictionary defines all available tasks, their rewards, cooldowns in seconds, and rank points.
# 'type' can be 'INSTANT' (like watching an ad) or 'QUIZ'.
# 'rank_points' represent user activity and engagement - they don't decrease on purchases
TASK_CONFIG = {
    # Daily login thing
    "daily_check_in": {"reward": 50, "rank_points": 3, "cooldown_seconds": 79200, "type": "INSTANT", "description": "Daily Check-In & Streak Bonus"},

    # Daily tasks thing
    "watch_ad": {"reward": 100, "rank_points": 1, "cooldown_seconds": 60, "type": "INSTANT", "description": "Watch a video ad"},
    "daily_tap": {"reward": 50, "rank_points": 2, "cooldown_seconds": 86400, "type": "INSTANT", "description": "Daily login bonus"},
    "quiz_game": {"reward": 75, "rank_points": 4, "cooldown_seconds": 300, "type": "QUIZ", "description": "Answer a quiz question"},
}


# --- DTOs (Data Transfer Objects) ---
class TaskInfo(BaseModel):
    task_id: str
    description: str
    reward: int
    rank_points: int
    type: str
    cooldown_seconds: int


class TaskComplete(BaseModel):
    task_id: str
    # For quizzes, this payload will contain the answer
    payload: Dict[str, Any] | None = None


class BalanceUpdateResponse(BaseModel):
    message: str
    new_balance: int
    new_rank_points: int
    rank_points_earned: int
    cooldown_expires_at: datetime | None = None


class TaskStatus(BaseModel):
    task_id: str
    description: str
    reward: int
    rank_points: int
    type: str
    cooldown_seconds: int
    is_available: bool
    cooldown_expires_at: datetime | None = None
    seconds_until_available: int | None = None


class QuizQuestionResponse(BaseModel):
    quizId: PydanticObjectId
    question: str
    options: List[str]

# --- Endpoints ---




@router.get("/all", response_model=List[TaskInfo])
async def get_all_tasks():
    """Lists all available task types in the game."""
    task_list = []
    for task_id, config in TASK_CONFIG.items():
        task_list.append(TaskInfo(task_id=task_id, **config))
    return task_list




@router.post("/complete", response_model=BalanceUpdateResponse)
@api_limiter.limit("20/minute")
async def complete_task(
    request: Request,
    completion_data: TaskComplete,
    current_user: User = Depends(get_current_verified_user)
):
    """
    A generic endpoint to mark a task as completed and claim a reward.
    The logic is determined by the task_id.
    """
    task_id = completion_data.task_id
    config = TASK_CONFIG.get(task_id)

    if not config:
        raise HTTPException(status_code=404, detail="Task not found")

    # --- Cooldown Check ---
    cooldown_expiry = current_user.task_cooldowns.get(task_id)
    if cooldown_expiry and datetime.utcnow() < cooldown_expiry:
        raise HTTPException(status_code=429, detail="Task is on cooldown. Try again later.")

    base_reward_amount = 0
    updates_to_set = {}

    # --- Task-specific Logic ---
    base_rank_points = config.get("rank_points", 0)
    
    if task_id == "daily_check_in":
        base_reward_amount = config["reward"]
        today = date.today()
        yesterday = today - timedelta(days=1)
        
        new_streak = 1
        # Check if the last check-in was yesterday to continue the streak
        if current_user.last_check_in_date and current_user.last_check_in_date == yesterday:
            new_streak = current_user.daily_streak + 1
        # If the last check-in was today, it's a redundant call, but we don't reset.
        elif current_user.last_check_in_date and current_user.last_check_in_date == today:
            new_streak = current_user.daily_streak
        # Otherwise, the streak resets to 1.
        
        # Calculate streak bonus (e.g., 10 HC per day, capped at 7 days)
        streak_bonus = min(new_streak, 7) * 10
        base_reward_amount += streak_bonus # Add bonus to base reward
        
        # Bonus rank points for streak (1 point per day of streak, capped at 7 days)
        streak_rank_bonus = min(new_streak, 7) * 1
        base_rank_points += streak_rank_bonus
        
        # Prepare the streak fields for updating
        updates_to_set[User.last_check_in_date] = today
        updates_to_set[User.daily_streak] = new_streak

    elif task_id == "watch_ad":
        base_reward_amount = config["reward"]
        # In a real app, you might have server-to-server ad validation logic here
        
    elif task_id == "daily_tap":
        base_reward_amount = config["reward"]

    elif task_id == "quiz_game":
        # This task type requires a payload with the quiz answer
        payload = completion_data.payload
        if not payload or "quizId" not in payload or "answerIndex" not in payload:
            raise HTTPException(status_code=400, detail="Must have payload with quizId and answerIndex")
        
        quiz = await Quiz.get(PydanticObjectId(payload["quizId"]))
        if not quiz:
            raise HTTPException(status_code=404, detail="Quiz not found")

        if quiz.correctAnswerIndex == payload["answerIndex"]:
            base_reward_amount = config["reward"]
            # Quiz gives full rank points for correct answers
        else:
            # Wrong answer gives no reward or rank points
            base_rank_points = 0
            # If wrong, update cooldown expiry but give no reward and return a specific message
            actual_cooldown_seconds = await GameLogic.calculate_task_cooldown(
                user=current_user,
                base_cooldown_seconds=config["cooldown_seconds"]
            )
            cooldown_expiry = datetime.utcnow() + timedelta(seconds=actual_cooldown_seconds)
            await current_user.update(Set({f"task_cooldowns.{task_id}": cooldown_expiry}))
            raise HTTPException(
                status_code=400, 
                detail={
                    "message": "Incorrect answer. No reward given.",
                    "cooldown_expires_at": cooldown_expiry.isoformat()
                }
            )

    else:
        raise HTTPException(status_code=400, detail="Unknown task completion logic.")

    # --- Grant Reward and Update Cooldown ---
    cooldown_expiry = None
    final_reward: int = 0
    final_rank_points: int = 0
    
    if base_reward_amount > 0:
        final_reward = await GameLogic.calculate_task_reward(
            user=current_user,
            base_reward=base_reward_amount
        )
    
    if base_rank_points > 0:
        final_rank_points = await GameLogic.calculate_rank_point_reward(
            user=current_user,
            base_rank_points=base_rank_points
        )

    # Set cooldown only if cooldown_seconds > 0
    if config["cooldown_seconds"] > 0:
        # Calculate actual cooldown with boosters applied
        actual_cooldown_seconds = await GameLogic.calculate_task_cooldown(
            user=current_user,
            base_cooldown_seconds=config["cooldown_seconds"]
        )
        cooldown_expiry = datetime.utcnow() + timedelta(seconds=actual_cooldown_seconds)
        updates_to_set[f"task_cooldowns.{task_id}"] = cooldown_expiry
    
    # Update user balance and rank points
    update_inc = {}
    if final_reward > 0:
        update_inc[User.hc_balance] = final_reward
        update_inc[User.hc_earned_in_level] = final_reward
    if final_rank_points > 0:
        update_inc[User.rank_points] = final_rank_points
    
    if update_inc or updates_to_set:
        if update_inc:
            await current_user.update(Inc(update_inc), Set(updates_to_set))
        else:
            await current_user.update(Set(updates_to_set))

    return BalanceUpdateResponse(
        message=f"Task '{task_id}' completed successfully!",
        new_balance=current_user.hc_balance + final_reward,
        new_rank_points=current_user.rank_points + final_rank_points,
        rank_points_earned=final_rank_points,
        cooldown_expires_at=cooldown_expiry
    )


async def _fetch_all_active_quizzes() -> List[Quiz]:
    """Fetch all active quizzes from database."""
    return await Quiz.find(Quiz.isActive == True).to_list()


# DOCS: Uses PyMongo here directly due to a bug that Motor/Beanie
#      has version mis-match with PyMongo. Bug is in Beanie or Motor.
@router.get("/quiz/fetch", response_model=QuizQuestionResponse)
async def fetch_quiz_question(current_user: User = Depends(get_current_verified_user)):
    """Fetches a random quiz question for the quiz_game task (cached for 30 minutes)."""
    user_lang = current_user.language

    # Get cached list of all active quizzes (or fetch if expired)
    all_quizzes = await quiz_cache.get_or_fetch(_fetch_all_active_quizzes)
    
    if not all_quizzes:
        raise HTTPException(status_code=404, detail="No active quizzes found.")
    
    # Select random quiz from cached list (in-memory operation, very fast)
    quiz = random.choice(all_quizzes)

    return QuizQuestionResponse(
        quizId=quiz.id,
        question=getattr(quiz, f"question_{user_lang}", quiz.question_en),
        options=getattr(quiz, f"options_{user_lang}", quiz.options_en)
    )


@router.get("/status", response_model=List[TaskStatus])
async def get_task_status(current_user: User = Depends(get_current_verified_user)):
    """Get the status of all tasks for the current user."""
    now = datetime.utcnow()
    task_statuses = []
    
    for task_id, config in TASK_CONFIG.items():
        cooldown_expires_at = current_user.task_cooldowns.get(task_id)
        is_available = cooldown_expires_at is None or now >= cooldown_expires_at
        
        seconds_until_available = None
        if not is_available and cooldown_expires_at:
            seconds_until_available = int((cooldown_expires_at - now).total_seconds())
            seconds_until_available = max(0, seconds_until_available)
        
        task_statuses.append(TaskStatus(
            task_id=task_id,
            description=config["description"],
            reward=config["reward"],
            rank_points=config["rank_points"],
            type=config["type"],
            cooldown_seconds=config["cooldown_seconds"],
            is_available=is_available,
            cooldown_expires_at=cooldown_expires_at,
            seconds_until_available=seconds_until_available
        ))
    
    return task_statuses




