class EmployeeHandbook:
    def __init__(self, company_name):
        """
        Initialize an Employee Handbook for a specific company.

        Parameters:
        - company_name (str): The name of the company.
        """
        self.company_name = company_name
        # Initialize the sections of the handbook with empty values
        self.sections = {
            "Company Values": [],
            "Code of Conduct": [],
            "Employee Benefits": [],
            "Attendance Policy": "",
            "Leave Policy": "",
            "Workplace Rules": [],
            "Termination Policy": "",
        }

    def add_company_value(self, value):
        """
        Add a core company value to the handbook.

        Parameters:
        - value (str): Description of a core company value.
        """
        # Append the value to the "Company Values" section
        self.sections["Company Values"].append(value)

    def add_code_of_conduct(self, conduct_rule):
        """
        Add a rule to the code of conduct section.

        Parameters:
        - conduct_rule (str): A specific rule or expectation for employee behavior.
        """
        # Append the conduct rule to the "Code of Conduct" section
        self.sections["Code of Conduct"].append(conduct_rule)

    def add_employee_benefit(self, benefit):
        """
        Add a benefit to the employee benefits section.

        Parameters:
        - benefit (str): Description of an employee benefit.
        """
        # Append the benefit to the "Employee Benefits" section
        self.sections["Employee Benefits"].append(benefit)

    def set_attendance_policy(self, policy):
        """
        Set the attendance policy.

        Parameters:
        - policy (str): Description of the attendance policy.
        """
        # Set the "Attendance Policy" section to the provided policy
        self.sections["Attendance Policy"] = policy

    def set_leave_policy(self, policy):
        """
        Set the leave policy.

        Parameters:
        - policy (str): Description of the leave policy.
        """
        # Set the "Leave Policy" section to the provided policy
        self.sections["Leave Policy"] = policy

    def add_workplace_rule(self, rule):
        """
        Add a workplace rule to the handbook.

        Parameters:
        - rule (str): A rule that employees are expected to follow in the workplace.
        """
        # Append the rule to the "Workplace Rules" section
        self.sections["Workplace Rules"].append(rule)

    def set_termination_policy(self, policy):
        """
        Set the termination policy for employees.

        Parameters:
        - policy (str): Description of the termination policy.
        """
        # Set the "Termination Policy" section to the provided policy
        self.sections["Termination Policy"] = policy

    def display_handbook(self):
        """
        Display the complete employee handbook.
        """
        print(f"=== Employee Handbook for {self.company_name} ===")

        # Display each section of the handbook
        print("\nCompany Values:")
        for value in self.sections["Company Values"]:
            print(f"  - {value}")

        print("\nCode of Conduct:")
        for rule in self.sections["Code of Conduct"]:
            print(f"  - {rule}")

        print("\nEmployee Benefits:")
        for benefit in self.sections["Employee Benefits"]:
            print(f"  - {benefit}")

        print("\nAttendance Policy:")
        print(f"  {self.sections['Attendance Policy']}")

        print("\nLeave Policy:")
        print(f"  {self.sections['Leave Policy']}")

        print("\nWorkplace Rules:")
        for rule in self.sections["Workplace Rules"]:
            print(f"  - {rule}")

        print("\nTermination Policy:")
        print(f"  {self.sections['Termination Policy']}")
