# core/translations.py
from typing import Dict, Any

# Translation dictionaries for different languages
TRANSLATIONS: Dict[str, Dict[str, str]] = {
    "en": {
        # Shop items
        "Speed Hustle": "Speed Hustle",
        "Completes all of your tasks 2x faster.": "Completes all of your tasks 2x faster.",
        "Double Coins": "Double Coins",
        "Doubles the HustleCoin (HC) you earn from tasks.": "Doubles the HustleCoin (HC) you earn from tasks.",
        "Power Prestige": "Power Prestige",
        "Increases Rank Point gains by 50% to help you climb the leaderboards.": "Increases Rank Point gains by 50% to help you climb the leaderboards.",
        "Hustler Brain": "Hustler Brain",
        "Reduces the cooldown on your tasks by 50%.": "Reduces the cooldown on your tasks by 50%.",
        "Land Multiplier": "Land Multiplier",
        "Boosts your passive land income by 100%.": "Boosts your passive land income by 100%.",
        "Safe Lock Recharger": "Safe Lock Recharger",
        "Instantly adds 5% to the community Safe Luck Fund.": "Instantly adds 5% to the community Safe Luck Fund.",
        "Combo Boost Pack": "Combo Boost Pack",
        "A high-value bundle containing Speed Hustle, Double Coins, and Power Prestige.": "A high-value bundle containing Speed Hustle, Double Coins, and Power Prestige.",
        "Bronze Key": "Bronze Key",
        "Unlocks access to basic spells, land, and boosters.": "Unlocks access to basic spells, land, and boosters.",
        "Silver Key": "Silver Key",
        "Unlocks rare spells, all lands, and special events.": "Unlocks rare spells, all lands, and special events.",
        "Gold Key": "Gold Key",
        "Unlocks VIP tasks and ranking boards.": "Unlocks VIP tasks and ranking boards.",
        "Platinum Key": "Platinum Key",
        "Grants full access to all features and VIP bonuses.": "Grants full access to all features and VIP bonuses.",
        "Permanent Key": "Permanent Key",
        "Grants lifetime full access and an elite title.": "Grants lifetime full access and an elite title.",
    },
    "pt": {
        # Shop items in Portuguese
        "Speed Hustle": "Hustle Rápido",
        "Completes all of your tasks 2x faster.": "Completa todas as suas tarefas 2x mais rápido.",
        "Double Coins": "Moedas Duplas",
        "Doubles the HustleCoin (HC) you earn from tasks.": "Dobra o HustleCoin (HC) que você ganha das tarefas.",
        "Power Prestige": "Prestígio Poderoso",
        "Increases Rank Point gains by 50% to help you climb the leaderboards.": "Aumenta os ganhos de Pontos de Ranking em 50% para ajudá-lo a subir nos rankings.",
        "Hustler Brain": "Cérebro Hustler",
        "Reduces the cooldown on your tasks by 50%.": "Reduz o tempo de espera das suas tarefas em 50%.",
        "Land Multiplier": "Multiplicador de Terra",
        "Boosts your passive land income by 100%.": "Aumenta sua renda passiva de terra em 100%.",
        "Safe Lock Recharger": "Recarregador do Cofre",
        "Instantly adds 5% to the community Safe Luck Fund.": "Adiciona instantaneamente 5% ao Fundo de Sorte da Comunidade.",
        "Combo Boost Pack": "Pacote Combo Boost",
        "A high-value bundle containing Speed Hustle, Double Coins, and Power Prestige.": "Um pacote de alto valor contendo Hustle Rápido, Moedas Duplas e Prestígio Poderoso.",
        "Bronze Key": "Chave de Bronze",
        "Unlocks access to basic spells, land, and boosters.": "Desbloqueia acesso a feitiços básicos, terra e reforços.",
        "Silver Key": "Chave de Prata",
        "Unlocks rare spells, all lands, and special events.": "Desbloqueia feitiços raros, todas as terras e eventos especiais.",
        "Gold Key": "Chave de Ouro",
        "Unlocks VIP tasks and ranking boards.": "Desbloqueia tarefas VIP e quadros de ranking.",
        "Platinum Key": "Chave de Platina",
        "Grants full access to all features and VIP bonuses.": "Concede acesso total a todos os recursos e bônus VIP.",
        "Permanent Key": "Chave Permanente",
        "Grants lifetime full access and an elite title.": "Concede acesso total vitalício e um título de elite.",
    }
}

def translate_text(text: str, language: str = "en") -> str:
    """
    Translate a given text to the specified language.
    If translation is not found, returns the original text.
    Language code is case-insensitive (e.g., 'pt', 'PT', 'Pt' all work).
    """
    # Normalize language code to lowercase
    normalized_language = language.lower()
    return TRANSLATIONS.get(normalized_language, {}).get(text, text)

def translate_list(items: list, language: str = "en") -> list:
    """
    Translate a list of items to the specified language.
    Language code is case-insensitive.
    """
    return [translate_text(item, language) for item in items]

def translate_dict_values(data: Dict[str, Any], language: str = "en") -> Dict[str, Any]:
    """
    Translate string values in a dictionary while keeping the structure intact.
    Only translates string values, leaves other types unchanged.
    Language code is case-insensitive.
    """
    translated = {}
    for key, value in data.items():
        if isinstance(value, str):
            translated[key] = translate_text(value, language)
        elif isinstance(value, list):
            translated[key] = translate_list(value, language)
        elif isinstance(value, dict):
            translated[key] = translate_dict_values(value, language)
        else:
            translated[key] = value
    return translated
