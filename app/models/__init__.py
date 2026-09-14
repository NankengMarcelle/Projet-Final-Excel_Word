# Importing every model here registers it on Base.metadata as a side effect,
# which is what lets Alembic's autogenerate (and anything importing this package)
# see the full schema without each model needing to know about its siblings.
from app.models.user import User  # noqa: F401
from app.models.workbook import Workbook  # noqa: F401
from app.models.worksheet import Worksheet  # noqa: F401
from app.models.sheet_relationship import SheetRelationship  # noqa: F401
from app.models.conversion import Conversion  # noqa: F401
from app.models.word_document import WordDocument  # noqa: F401
