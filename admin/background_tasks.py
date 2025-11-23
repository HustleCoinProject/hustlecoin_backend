# admin/background_tasks.py
from typing import List, Dict
from beanie import PydanticObjectId
from data.models.models import Payout
from .crud import bulk_process_payouts


async def process_payouts_background(payouts_to_process: List[Dict], admin_username: str):
    """Process payouts in background after CSV validation."""
    try:
        print(f"[BACKGROUND] Processing {len(payouts_to_process)} payouts for {admin_username}")
        
        # Re-validate payouts are still pending (prevents duplicates)
        valid_payouts = []
        for payout_data in payouts_to_process:
            try:
                payout = await Payout.get(PydanticObjectId(payout_data['payout_id']))
                if payout and payout.status == 'pending':
                    valid_payouts.append(payout_data)
            except Exception:
                pass  # Skip invalid payouts
        
        if valid_payouts:
            results = await bulk_process_payouts(valid_payouts, admin_username)
            print(f"[BACKGROUND] Completed: {results['processed']} processed, {results['failed']} failed")
        else:
            print(f"[BACKGROUND] No valid payouts remaining to process")
            
    except Exception as e:
        print(f"[BACKGROUND] Error: {str(e)}")