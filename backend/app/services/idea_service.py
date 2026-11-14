from app.utils.logger import logger


class Idea:
    def __init__(self, model, *args, **kwargs):
        logger.info("Idea Object created.")  # Log the creation of Idea object
        self._model = model  # First argument is mandatory and assigned to 'model'
        self._description = args[0] if args else None  # Optional second argument
        self.kwargs = kwargs  # Any additional keyword arguments

    @property
    def model(self):
        logger.debug(f"Accessing model: {self._model}")  # Log the access to 'model' property
        return self._model

    @model.setter
    def model(self, value):
        logger.info(f"Setting model: {value}")  # Log the setting of 'model' property
        self._model = value

    @property
    def description(self):
        logger.debug(
            f"Accessing description: {self._description}"
        )  # Log the access to 'description' property
        return self._description

    @description.setter
    def description(self, value):
        logger.info(f"Setting description: {value}")  # Log the setting of 'description' property
        self._description = value

    def get_summary(self):
        """
        Retrieve a summary of the idea using the AI layer in the model.
        """
        # Check if the model has '_ai_layer' attribute and 'generate_summary' method
        if hasattr(self._model, "_ai_layer") and hasattr(self._model._ai_layer, "generate_summary"):
            try:
                logger.info(
                    "Generating summary using AI layer..."
                )  # Log the start of summary generation
                return self._model._ai_layer.generate_summary(self._description)
            except Exception as e:
                logger.error(
                    f"Failed to generate summary from AI layer: {e}"
                )  # Log any error during summary generation
                return None
        else:
            logger.warning(
                "Model is missing _ai_layer or generate_summary method."
            )  # Log the absence of required attribute or method
            return None
