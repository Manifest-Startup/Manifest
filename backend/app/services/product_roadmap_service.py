from datetime import datetime

from app.utils.logger import logger


class ProductRoadmap:
    def __init__(self, product_name):
        """
        Initialize a Product Roadmap for a specific product.

        Parameters:
        - product_name (str): The name of the product.
        """
        self.product_name = product_name
        self.milestones = []  # Initialize an empty list to store milestones

    def add_milestone(self, milestone_name, description, estimated_completion, responsible_team):
        """
        Add a new milestone to the product roadmap.

        Parameters:
        - milestone_name (str): The name of the milestone.
        - description (str): A short description of the milestone.
        - estimated_completion (str): Estimated completion date (format: 'YYYY-MM-DD').
        - responsible_team (str): The team or individual responsible for the milestone.

        Returns:
        - str: A message indicating the addition status.
        """
        try:
            # Convert the estimated_completion string to a datetime object
            completion_date = datetime.strptime(estimated_completion, "%Y-%m-%d")
        except ValueError:
            return "Invalid date format. Please use 'YYYY-MM-DD'."

        # Create a new milestone dictionary
        milestone = {
            "Milestone Name": milestone_name,
            "Description": description,
            "Estimated Completion": completion_date,
            "Responsible Team": responsible_team,
            "Features": [],  # Initialize an empty list to store features
        }
        self.milestones.append(milestone)  # Add the new milestone to the milestones list
        return f"Milestone '{milestone_name}' has been added."

    def add_feature_to_milestone(self, milestone_name, feature_name, feature_description):
        """
        Add a feature to a specific milestone.

        Parameters:
        - milestone_name (str): The name of the milestone.
        - feature_name (str): The name of the feature.
        - feature_description (str): A short description of the feature.

        Returns:
        - str: A message indicating the addition status.
        """
        for milestone in self.milestones:  # Iterate over each milestone in the milestones list
            if milestone["Milestone Name"] == milestone_name:  # If the milestone name matches
                # Add the new feature to the milestone's features list
                milestone["Features"].append(
                    {"Feature Name": feature_name, "Description": feature_description}
                )
                return f"Feature '{feature_name}' has been added to milestone '{milestone_name}'."
        return f"Milestone '{milestone_name}' not found."  # If no matching milestone was found

    def display_roadmap(self):
        """
        Display the entire product roadmap.
        """
        print(f"=== Product Roadmap for {self.product_name} ===")
        for milestone in self.milestones:  # Iterate over each milestone in the milestones list
            # Convert the milestone's completion date to a string
            completion_date = milestone["Estimated Completion"].strftime("%Y-%m-%d")
            print(f"\nMilestone: {milestone['Milestone Name']}")
            print(f"Description        : {milestone['Description']}")
            print(f"Estimated Completion : {completion_date}")
            print(f"Responsible Team   : {milestone['Responsible Team']}")
            print("Features:")
            for feature in milestone[
                "Features"
            ]:  # Iterate over each feature in the milestone's features list
                print(f"  - {feature['Feature Name']}: {feature['Description']}")
            print("---------------------------------------------------")

    def update_milestone_date(self, milestone_name, new_date):
        """
        Update the estimated completion date of a milestone.

        Parameters:
        - milestone_name (str): The name of the milestone.
        - new_date (str): The new estimated completion date (format: 'YYYY-MM-DD').

        Returns:
        - str: A message indicating the update status.
        """
        try:
            # Convert the new_date string to a datetime object
            new_completion_date = datetime.strptime(new_date, "%Y-%m-%d")
        except ValueError:
            return "Invalid date format. Please use 'YYYY-MM-DD'."

        for milestone in self.milestones:  # Iterate over each milestone in the milestones list
            if milestone["Milestone Name"] == milestone_name:  # If the milestone name matches
                # Update the milestone's completion date
                milestone["Estimated Completion"] = new_completion_date
                return (
                    f"Milestone '{milestone_name}' completion date has been updated to {new_date}."
                )
        return f"Milestone '{milestone_name}' not found."  # If no matching milestone was found

    def remove_milestone(self, milestone_name):
        """
        Remove a milestone from the product roadmap.

        Parameters:
        - milestone_name (str): The name of the milestone to remove.

        Returns:
        - str: A message indicating the removal status.
        """
        for milestone in self.milestones:  # Iterate over each milestone in the milestones list
            if milestone["Milestone Name"] == milestone_name:  # If the milestone name matches
                self.milestones.remove(milestone)  # Remove the milestone from the milestones list
                return f"Milestone '{milestone_name}' has been removed."
        return f"Milestone '{milestone_name}' not found."  # If no matching milestone was found

    def generate(self):
        """
        Generate a default product development roadmap with predefined milestones.
        This function simulates generation and can be later extended to use AI.
        """
        from datetime import timedelta

        logger.info(
            "Generating default product roadmap."
        )  # Log the start of the generation process
        today = datetime.today()  # Get the current date
        # Define a list of default milestones
        default_milestones = [
            {
                "milestone_name": "MVP Planning",
                "description": "Define MVP scope and resources.",
                "days_ahead": 30,
                "team": "Product Team",
            },
            {
                "milestone_name": "MVP Development",
                "description": "Build and integrate MVP features.",
                "days_ahead": 90,
                "team": "Engineering Team",
            },
            {
                "milestone_name": "Beta Release",
                "description": "Launch beta version and gather user feedback.",
                "days_ahead": 150,
                "team": "QA and Product Team",
            },
            {
                "milestone_name": "Public Launch",
                "description": "Release product to the general public.",
                "days_ahead": 210,
                "team": "Marketing and Engineering",
            },
        ]

        for milestone in default_milestones:  # Iterate over each default milestone
            # Calculate the estimated completion date for the milestone
            estimated_completion = (today + timedelta(days=milestone["days_ahead"])).strftime(
                "%Y-%m-%d"
            )
            # Add the milestone to the roadmap
            result = self.add_milestone(
                milestone_name=milestone["milestone_name"],
                description=milestone["description"],
                estimated_completion=estimated_completion,
                responsible_team=milestone["team"],
            )
            logger.info(result)  # Log the result of adding the milestone

        logger.info("Default roadmap generation complete.")  # Log the end of the generation process
        return "Default roadmap generated."
