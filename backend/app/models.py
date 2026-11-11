"""Import every model so Alembic and tests see the full schema."""
from app.audit.models import AuditEvent  # noqa: F401
from app.foods.models import Food, FoodPortion  # noqa: F401
from app.meals.models import Meal, MealItem, MealProposal, MealProposalItem  # noqa: F401
from app.targets.models import NutritionTarget  # noqa: F401
from app.users.models import User  # noqa: F401
from app.messaging.models import Message  # noqa: F401
from app.reminders.models import Reminder  # noqa: F401
