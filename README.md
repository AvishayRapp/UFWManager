UFW Firewall Manager: The TUI for Uncomplicated Firewall
UFW Manager is a terminal UI for the Uncomplicated Firewall (ufw) on Linux, providing an interactive way to manage firewall rules without complex commands.

Why Use UFW Manager?
While ufw is powerful, managing rules in the terminal is cumbersome. UFW Manager provides a visual overview of your rules, an intuitive form-based editor to prevent typos, and adds crucial features like persistent notes and service descriptions for each rule, so you always remember its purpose. It also includes a "Panic Mode" to safely reset the firewall if you get locked out.

Features
View, add, edit, and delete rules through an interactive, scrollable list. A guided form with dropdowns simplifies rule creation, while persistent notes and service descriptions are saved in ~/.config/ufwnotes/. The script is a single lightweight Python file and includes a "Panic Mode" for safety.

Screenshots
Main Window

Add/Edit Rule Window

Setup
Requirements: Linux with UFW, Python 3.6+, and sudo access.

Installation:

Save the code as ufwmanager.py.

Make it executable: chmod +x ufwmanager.py.

Run with sudo: sudo ./ufwmanager.py.

Keybindings
Key

Action

↑ / ↓

Navigate through the rule list.

A

Open the "Add Rule" window.

D

Delete the selected rule (with confirmation).

ENTER

Open the "Edit Rule" window for the selected rule.

R

Reload the firewall and refresh the rule list.

Shift + P

Activate "Panic Mode" to reset the firewall.

Q

Quit the application.

