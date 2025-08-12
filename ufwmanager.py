#!/usr/bin/env python3

import curses
import subprocess
import re
import os
from datetime import datetime
from typing import List, Optional, Tuple

class UFWManager:
    """
    A terminal-based TUI for managing the UFW (Uncomplicated Firewall).
    """
    def __init__(self):
        # UI State
        self.selected_index = 0
        self.scroll_pos = 0
        self.status_message = "Welcome to UFW Manager! Press 'R' to load/reload rules."
        
        # Data
        self.rules: List[List[str]] = []
        self.ufw_status = "inactive"
        
        self.notes_dir = os.path.expanduser("~/.config/ufwnotes")
        self.notes_file = os.path.join(self.notes_dir, "notes.txt")
        self.services_file = os.path.join(self.notes_dir, "services.txt")
        self.notes: dict[str, str] = {}
        self.services: dict[str, str] = {}
        self._setup_and_load_files()

    # --- UFW & Notes Core Functions ---

    def _run_command(self, command: str, needs_input: Optional[str] = None) -> subprocess.CompletedProcess:
        """A helper to run shell commands and handle sudo."""
        if needs_input:
            command = f"echo '{needs_input}' | {command}"
        
        return subprocess.run(
            command, 
            shell=True, 
            check=True, 
            capture_output=True, 
            text=True
        )

    def _setup_and_load_files(self):
        """Creates the notes/services directory/files if needed, then loads them."""
        try:
            os.makedirs(self.notes_dir, exist_ok=True)
            for file_path, data_dict in [(self.notes_file, self.notes), (self.services_file, self.services)]:
                if not os.path.isfile(file_path):
                    open(file_path, 'a').close()
                
                data_dict.clear()
                with open(file_path, 'r') as f:
                    for line in f:
                        if ':' in line:
                            num, text = line.split(':', 1)
                            if num.strip().isdigit():
                                data_dict[num.strip()] = text.strip()
        except (OSError, PermissionError) as e:
            self.status_message = f"Error with config files: {e}"

    def _save_notes_or_services(self, file_path: str, data_dict: dict):
        """Saves a given dictionary to its corresponding file."""
        try:
            with open(file_path, 'w') as f:
                valid_items = [item for item in data_dict.items() if item[0].isdigit()]
                for num, text in sorted(valid_items, key=lambda item: int(item[0])):
                    f.write(f"{num}:{text}\n")
        except (OSError, PermissionError) as e:
            self.status_message = f"Error saving to {os.path.basename(file_path)}: {e}"
            
    def _get_firewall_rules(self):
        """Fetches and parses numbered UFW rules and status."""
        try:
            result = self._run_command("sudo ufw status numbered")
            lines = result.stdout.strip().split('\n')
            status_line = next((line for line in lines if "Status:" in line), "Status: inactive")
            self.ufw_status = status_line.split(':')[1].strip()
            
            self.rules = []
            for line in lines:
                line = line.strip()
                match = re.match(r'(\[\s*\d+\])\s+(.*)', line)
                if match:
                    self.rules.append([match.group(1), match.group(2)])

            if not self.rules:
                self.status_message = "UFW is active, but no rules are configured."
        except subprocess.CalledProcessError:
            self.ufw_status = "error"
            self.rules = []
            self.status_message = "Error fetching UFW status. Is it installed and enabled?"

    def _reload_firewall(self):
        """Reloads the UFW firewall and refreshes the rule list."""
        try:
            self._run_command("sudo ufw reload")
            self.status_message = "Firewall reloaded successfully."
        except subprocess.CalledProcessError as e:
            self.status_message = f"Error reloading firewall: {e.stderr.strip()}"
        self._get_firewall_rules()

    def _delete_firewall_rule(self, stdscr):
        """Deletes the currently selected firewall rule and its associated note/service."""
        if not self.rules or self.selected_index >= len(self.rules):
            self.status_message = "No rule selected to delete."
            return
        
        rule_num_str = self.rules[self.selected_index][0].strip('[] ')
        if not rule_num_str.isdigit():
             self.status_message = "This line is not a deletable rule."
             return
             
        if self._confirm_action(stdscr, f"Delete rule #{rule_num_str}?"):
            try:
                self._run_command(f"sudo ufw delete {rule_num_str}", needs_input='y')
                self.status_message = f"Rule {rule_num_str} deleted successfully."
                
                deleted_num = int(rule_num_str)
                for data_dict, file_path in [(self.notes, self.notes_file), (self.services, self.services_file)]:
                    new_data = {}
                    for num_str, text in data_dict.items():
                        num = int(num_str)
                        if num == deleted_num: continue
                        if num > deleted_num: new_data[str(num - 1)] = text
                        else: new_data[num_str] = text
                    if data_dict == self.notes: self.notes = new_data
                    else: self.services = new_data
                    self._save_notes_or_services(file_path, new_data)

                self.selected_index = max(0, self.selected_index - 1)
                self._get_firewall_rules()
            except subprocess.CalledProcessError as e:
                self.status_message = f"Error deleting rule: {e.stderr.strip()}"

    def _add_or_edit_rule(self, stdscr, is_edit: bool = False):
        """Opens a window to add or edit a rule, then applies it."""
        rule_to_edit = None
        old_rule_num = None
        if is_edit:
            if not self.rules or self.selected_index >= len(self.rules):
                self.status_message = "No rule selected to edit."; return
            rule_to_edit = self.rules[self.selected_index]
            old_rule_num = rule_to_edit[0].strip('[] ')

        result = self._get_rule_input_from_form(stdscr, rule_to_edit)
        if result:
            new_rule_command, service_text, note_text = result
            try:
                if is_edit:
                    self._run_command(f"sudo ufw delete {old_rule_num}", needs_input='y')
                    self._run_command(f"sudo ufw insert {old_rule_num} {new_rule_command}")
                    
                    for num, text, data_dict, file_path in [(old_rule_num, service_text, self.services, self.services_file), (old_rule_num, note_text, self.notes, self.notes_file)]:
                        if text: data_dict[num] = text
                        elif num in data_dict: del data_dict[num]
                        self._save_notes_or_services(file_path, data_dict)
                else:
                    old_rules_set = {tuple(r) for r in self.rules}
                    self._run_command(f"sudo ufw {new_rule_command}")
                    
                    self._get_firewall_rules()
                    new_rules_set = {tuple(r) for r in self.rules}
                    added_rules = new_rules_set - old_rules_set
                    
                    if added_rules:
                        new_rule_num = added_rules.pop()[0].strip('[] ')
                        if service_text: self.services[new_rule_num] = service_text; self._save_notes_or_services(self.services_file, self.services)
                        if note_text: self.notes[new_rule_num] = note_text; self._save_notes_or_services(self.notes_file, self.notes)

                self.status_message = "Rule applied successfully."
                self._get_firewall_rules()
            except subprocess.CalledProcessError as e:
                self.status_message = f"Error applying rule: {e.stderr.strip()}"

    def _panic_mode(self, stdscr):
        """Displays a confirmation window for resetting the firewall."""
        win = self._create_centered_win(stdscr, 8, 50)
        win.keypad(True)
        
        h, w = win.getmaxyx()

        title = "!!! PANIC MODE !!!"
        line2 = "THIS WILL RESET THE FIREWALL TO DEFAULTS!"
        line3 = "ONLY USE IF SOMETHING WENT WRONG."
        line5 = "PRESS --- ENTER --- TO CONTINUE..."
        line6 = "PRESS --- ESC --- TO ABORT!"

        win.attron(curses.color_pair(2) | curses.A_BOLD)
        win.addstr(1, (w - len(title)) // 2, title)
        win.attroff(curses.color_pair(2) | curses.A_BOLD)

        win.addstr(2, (w - len(line2)) // 2, line2)
        win.addstr(3, (w - len(line3)) // 2, line3)
        
        win.addstr(5, (w - len(line5)) // 2, line5)
        win.addstr(6, (w - len(line6)) // 2, line6)
        win.refresh()

        while True:
            key = win.getch()
            if key in [curses.KEY_ENTER, 10, 13]:
                try:
                    self._run_command("sudo ufw reset", needs_input='y')
                    self.status_message = "Firewall has been reset to default."
                    self._get_firewall_rules()
                except subprocess.CalledProcessError as e:
                    self.status_message = f"Error resetting firewall: {e.stderr.strip()}"
                break
            elif key == 27: # Escape key
                self.status_message = "Panic mode aborted."
                break

    # --- UI & Input Forms ---

    def _create_centered_win(self, stdscr, h: int, w: int):
        """Helper to create a bordered, centered window."""
        height, width = stdscr.getmaxyx()
        y, x = (height - h) // 2, (width - w) // 2
        win = curses.newwin(h, w, y, x)
        win.box()
        return win

    def _confirm_action(self, stdscr, message: str) -> bool:
        """Displays a 'yes/no' confirmation dialog."""
        win = self._create_centered_win(stdscr, 5, 60)
        win.addstr(1, 2, message, curses.A_BOLD)
        win.addstr(2, 2, "Are you sure? (y/N): ")
        curses.echo(); curses.curs_set(1)
        try: user_input = win.getstr(2, 24, 3).decode('utf-8').strip().lower()
        except curses.error: user_input = ""
        curses.noecho(); curses.curs_set(0)
        return user_input == 'y'

    def _get_rule_input_from_form(self, stdscr, existing_rule: Optional[List[str]] = None) -> Optional[Tuple[str, str, str]]:
        """A form-based window to get input for a new or edited UFW rule."""
        win = self._create_centered_win(stdscr, 19, 60)
        win.keypad(True)
        win.addstr(1, 2, "Add/Edit UFW Rule (Use ←/→ for dropdowns)", curses.A_BOLD)
        
        actions, protocols, directions = ["allow", "deny", "reject", "limit"], ["tcp", "udp", "any"], ["in", "out"]
        fields = {"Action": [actions, 0], "Direction": [directions, 0], "Protocol": [protocols, 0], "Port": "", "From/To IP": "any", "Service": "", "Note": ""}
        field_order = ["Action", "Direction", "Protocol", "Port", "From/To IP", "Service", "Note"]
        
        if existing_rule:
            rule_num = existing_rule[0].strip('[] ')
            rule_text = existing_rule[1].lower()
            for i, action in enumerate(actions):
                if action in rule_text: fields["Action"][1] = i
            for i, direction in enumerate(directions):
                if f" {direction} " in rule_text: fields["Direction"][1] = i
            port_match = re.search(r'(\d+)', rule_text)
            if port_match: fields["Port"] = port_match.group(1)
            
            action_match = re.search(r'\b(allow|deny|reject|limit)\b(\s+in)?(\s+out)?', rule_text)
            if action_match:
                action_str = action_match.group(0)
                from_part = rule_text.split(action_str, 1)[1].strip()
                from_ip = from_part.split()[0]
                if from_ip and from_ip.lower() != 'anywhere':
                    fields["From/To IP"] = from_ip

            fields["Service"] = self.services.get(rule_num, "")
            fields["Note"] = self.notes.get(rule_num, "")

        current_field_idx = 0
        curses.curs_set(1)
        while True:
            y_offset = 3
            for i, name in enumerate(field_order):
                value = fields[name]
                is_dropdown = isinstance(value, list)
                
                attr = curses.A_REVERSE if i == current_field_idx else curses.A_NORMAL
                win.addstr(y_offset, 2, f"{name.ljust(10)}:", attr)
                
                win.attron(curses.color_pair(6))
                if name == "Action":
                    display_val = f"< {value[0][value[1]]} >"
                    win.addstr(y_offset, 14, f"{display_val:<10}")
                elif name in ["Direction", "Protocol"]:
                    display_val = f"< {value[0][value[1]]} >"
                    win.addstr(y_offset, 14, f"{display_val:<7}")
                elif name == "Port":
                    win.addstr(y_offset, 14, f"{value:<5}")
                elif name == "From/To IP":
                    win.addstr(y_offset, 14, f"{value:<15}")
                elif name == "Service":
                    win.addstr(y_offset, 14, f"{value:<18}")
                else: # Note
                    win.addstr(y_offset, 14, f"{value:<43}")
                win.attroff(curses.color_pair(6))
                
                win.hline(y_offset + 1, 2, curses.ACS_HLINE, 56)
                y_offset += 2

            win.addstr(y_offset, 2, "ESC - Close without saving | Enter - Save & close", curses.A_DIM)

            current_field_name = field_order[current_field_idx]
            if not isinstance(fields[current_field_name], list):
                win.move(3 + (current_field_idx * 2), 14 + len(fields[current_field_name]))
            
            win.refresh()
            key = win.getch()
            
            if key in [curses.KEY_ENTER, 10, 13]: break
            if key == 27: return None
            
            if key in [curses.KEY_UP, curses.KEY_BTAB]: current_field_idx = (current_field_idx - 1 + len(field_order)) % len(field_order)
            elif key in [curses.KEY_DOWN, ord('\t')]: current_field_idx = (current_field_idx + 1) % len(field_order)
            elif isinstance(fields[current_field_name], list):
                options, current_idx = fields[current_field_name]
                if key == curses.KEY_LEFT: fields[current_field_name][1] = (current_idx - 1 + len(options)) % len(options)
                elif key == curses.KEY_RIGHT: fields[current_field_name][1] = (current_idx + 1) % len(options)
            else:
                if key in [curses.KEY_BACKSPACE, 127, 8]: fields[current_field_name] = fields[current_field_name][:-1]
                elif 32 <= key <= 126:
                    if current_field_name == "Port" and len(fields[current_field_name]) >= 5: continue
                    if current_field_name == "From/To IP" and len(fields[current_field_name]) >= 15: continue
                    if current_field_name == "Service" and len(fields[current_field_name]) >= 18: continue
                    if current_field_name == "Note" and len(fields[current_field_name]) >= 43: continue
                    fields[current_field_name] += chr(key)
        
        curses.curs_set(0)
        
        action, direction, protocol = fields["Action"][0][fields["Action"][1]], fields["Direction"][0][fields["Direction"][1]], fields["Protocol"][0][fields["Protocol"][1]]
        port, from_ip, service, note = fields["Port"], fields["From/To IP"], fields["Service"], fields["Note"]

        if not port.isdigit(): self.status_message = "Error: Port must be a number."; return None

        rule = f"{action} {direction}"
        if from_ip.lower() != 'any': rule += f" from {from_ip}"
        rule += f" to any port {port}"
        if protocol.lower() != 'any': rule += f" proto {protocol}"
        
        return (rule, service, note)

    # --- UI Drawing ---

    def _setup_colors(self):
        curses.start_color(); curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_GREEN, -1); curses.init_pair(2, curses.COLOR_RED, -1)
        curses.init_pair(3, curses.COLOR_YELLOW, -1); curses.init_pair(4, curses.COLOR_CYAN, -1)
        curses.init_pair(5, curses.COLOR_WHITE, curses.COLOR_BLUE)
        curses.init_pair(6, curses.COLOR_WHITE, curses.COLOR_RED) # For editable fields

    def _draw_header(self, stdscr, width: int):
        timestamp, title = datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "UFW Firewall Manager"
        status_text, status_color = f"Status: {self.ufw_status.upper()}", 1 if self.ufw_status == 'active' else 2
        stdscr.attron(curses.color_pair(4) | curses.A_BOLD); stdscr.addstr(0, 2, title); stdscr.attroff(curses.color_pair(4) | curses.A_BOLD)
        stdscr.addstr(0, (width - len(timestamp)) - 2, timestamp)
        stdscr.attron(curses.color_pair(status_color) | curses.A_BOLD); stdscr.addstr(0, (width - len(status_text)) // 2, status_text); stdscr.attroff(curses.color_pair(status_color) | curses.A_BOLD)

    def _draw_main_window(self, stdscr, height: int, width: int):
        win = stdscr.subwin(height - 5, width, 2, 0); win.erase(); win.box()
        
        if self.ufw_status == 'error': win.addstr(2, 2, "Could not get UFW status. Is it installed?", curses.color_pair(2)); win.refresh(); return

        col_widths = {'#': 5, 'TO': 17, 'ACTION': 12, 'FROM/TO': 15, 'SERVICE': 18, 'NOTE': 5}
        header_str = (f"{'[#]':<{col_widths['#']}} "
                      f"{'TO':<{col_widths['TO']}} "
                      f"{'ACTION':<{col_widths['ACTION']}} "
                      f"{'FROM/TO':<{col_widths['FROM/TO']}} "
                      f"{'SERVICE':<{col_widths['SERVICE']}} "
                      f"{'NOTE'}")
        win.addstr(1, 2, header_str[:width-3], curses.A_BOLD)
        win.hline(2, 2, curses.ACS_HLINE, width - 4)

        if not self.rules: win.addstr(4, 2, "No rules to display."); win.refresh(); return

        list_height = (height - 9) // 2 
        if self.selected_index < self.scroll_pos: self.scroll_pos = self.selected_index
        if self.selected_index >= self.scroll_pos + list_height: self.scroll_pos = self.selected_index - list_height + 1

        y_pos = 3
        for i, rule in enumerate(self.rules[self.scroll_pos : self.scroll_pos + list_height]):
            is_selected = i + self.scroll_pos == self.selected_index
            
            rule_num, rule_details = rule[0], rule[1]
            rule_num_str = rule_num.strip("[] ")
            note_display = "Yes" if rule_num_str in self.notes else "No"
            service = self.services.get(rule_num_str, "")

            to_part, action_part, from_part = rule_details, "", ""
            action_match = re.search(r'\b(ALLOW|DENY|REJECT|LIMIT)\b(\s+IN)?(\s+OUT)?', rule_details)
            if action_match:
                action_str = action_match.group(0)
                parts = rule_details.split(action_str, 1)
                to_part = parts[0].strip()
                action_part = action_str.strip()
                from_full = parts[1].strip()
                from_part = from_full.split()[0]
            else: 
                to_part = rule_details

            line = (f"{rule_num:<{col_widths['#']}} "
                    f"{to_part:<{col_widths['TO']}} "
                    f"{action_part:<{col_widths['ACTION']}} "
                    f"{from_part:<{col_widths['FROM/TO']}} "
                    f"{service:<{col_widths['SERVICE']}} "
                    f"{note_display}")
            
            if is_selected:
                win.addstr(y_pos, 2, " " * (width - 4), curses.color_pair(5))
                win.addstr(y_pos, 2, line[:width-4], curses.color_pair(5) | curses.A_BOLD)
            else:
                win.addstr(y_pos, 2, line[:width-4])
            
            if y_pos + 1 < height - 5:
                 win.hline(y_pos + 1, 2, curses.ACS_HLINE, width - 4)
            y_pos += 2
        
        if self.scroll_pos + list_height < len(self.rules):
            scroll_text = "... ↓ Scroll for More ↓ ..."
            win.addstr(height - 7, (width - len(scroll_text)) // 2, scroll_text, curses.A_DIM)

    def _draw_footer(self, stdscr, height: int, width: int):
        footer_win = stdscr.subwin(3, width, height - 3, 0); footer_win.erase()
        
        keys_left = "↑/↓|A:Add|D:Del|ENT:Edit|R:Reload|Q:Quit"
        footer_win.addstr(2, 1, keys_left)

        keys_right = "Shift+P: Panic Mode!!"
        start_x = width - len(keys_right) - 2
        if start_x > len(keys_left):
            footer_win.attron(curses.color_pair(2) | curses.A_BOLD)
            footer_win.addstr(2, start_x, keys_right)
            footer_win.attroff(curses.color_pair(2) | curses.A_BOLD)

        if self.status_message:
            footer_win.addstr(0, 1, ' ' * (width-2))
            footer_win.addstr(0, 1, f"Status: {self.status_message}"[:width-2], curses.color_pair(3))
            self.status_message = ""

    # --- Main Application Loop ---

    def _app_loop(self, stdscr):
        curses.curs_set(0); stdscr.nodelay(1); stdscr.timeout(1000)
        self._setup_colors()

        h, w = stdscr.getmaxyx()
        loading_text = "UFW Firewall Manager loading..."
        stdscr.clear()
        stdscr.addstr(h // 2, (w - len(loading_text)) // 2, loading_text)
        stdscr.refresh()
        
        self._get_firewall_rules()

        while True:
            h, w = stdscr.getmaxyx()
            if h < 15 or w < 80:
                stdscr.clear(); stdscr.addstr(0, 0, "Terminal too small"); stdscr.refresh()
                if stdscr.getch() == ord('q'): break
                continue

            key = stdscr.getch()
            if key in [ord('q'), ord('Q')]: break

            if key == curses.KEY_UP: self.selected_index = max(0, self.selected_index - 1)
            elif key == curses.KEY_DOWN and self.rules: self.selected_index = min(len(self.rules) - 1, self.selected_index + 1)
            elif key in [ord('r'), ord('R')]: self._reload_firewall()
            elif key in [ord('d'), ord('D')]: self._delete_firewall_rule(stdscr)
            elif key in [ord('a'), ord('A')]: self._add_or_edit_rule(stdscr, is_edit=False)
            elif key in [curses.KEY_ENTER, 10, 13]: self._add_or_edit_rule(stdscr, is_edit=True)
            elif key == ord('P'): self._panic_mode(stdscr)
            if key == -1: 
                self._get_firewall_rules()
                self._setup_and_load_files()

            stdscr.erase(); self._draw_header(stdscr, w); self._draw_main_window(stdscr, h, w); self._draw_footer(stdscr, h, w); stdscr.refresh()

    def run(self):
        try:
            curses.wrapper(self._app_loop)
        except KeyboardInterrupt: pass
        finally:
            # --- MODIFIED: Clear screen and print a graceful exit message ---
            os.system('clear')
            print("\n=== UFW Manager terminated gracefully ===\n")

if __name__ == "__main__":
    UFWManager().run()
