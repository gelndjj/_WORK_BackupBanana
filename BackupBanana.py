# BackupBanana
#
# MIT License
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import os, shutil, json, schedule, time, sys
from datetime import datetime
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTime
from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
                             QFileDialog, QMessageBox, QProgressBar, QListWidget, QTabWidget, QLineEdit,
                             QListWidgetItem, QComboBox, QTimeEdit, QSplitter, QStyleFactory, QSystemTrayIcon, QMenu)
from PyQt5.QtGui import QIcon

class BackupThread(QThread):
    progress_update = pyqtSignal(int)
    backup_finished = pyqtSignal(dict)
    error_occurred = pyqtSignal(list)

    def __init__(self, source, destination, parent=None):
        super().__init__(parent)
        self.source = source
        self.destination = destination
        self.error_log = []

    def run(self):
        try:
            if not os.path.exists(self.destination):
                raise Exception("Destination directory is not reachable.")

            total_files = sum([len(files) for r, d, files in os.walk(self.source)])
            copied_files = 0
            copied_files_list = []
            modified_files_list = []
            copied_folders_list = []
            modified_folders_list = []

            for root, dirs, files in os.walk(self.source):
                relative_path = os.path.relpath(root, self.source)
                dest_path = os.path.join(self.destination, relative_path)
                if not os.path.exists(dest_path):
                    os.makedirs(dest_path)
                    copied_folders_list.append(dest_path)
                else:
                    modified_folders_list.append(dest_path)

                for file in files:
                    source_file = os.path.join(root, file)
                    dest_file = os.path.join(dest_path, file)
                    try:
                        if not os.path.exists(dest_file):
                            copied_files_list.append(dest_file)
                        elif os.path.getmtime(source_file) > os.path.getmtime(dest_file):
                            modified_files_list.append(dest_file)
                        shutil.copy2(source_file, dest_file)
                    except Exception as e:
                        self.error_log.append(f"Error copying {source_file} to {dest_file}: {str(e)}")

                    copied_files += 1
                    progress = int((copied_files / total_files) * 100)
                    self.progress_update.emit(progress)

            result = {
                "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "copied_files": len(copied_files_list),
                "modified_files": len(modified_files_list),
                "copied_folders": len(copied_folders_list),
                "modified_folders": len(modified_folders_list),
                "source": self.source,
                "destination": self.destination,
                "errors": self.error_log
            }
            self.backup_finished.emit(result)

        except Exception as e:
            self.error_occurred.emit([str(e)])

class SchedulerThread(QThread):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.scheduler = schedule.Scheduler()
        self.running = True

    def run(self):
        while self.running:
            self.scheduler.run_pending()
            time.sleep(1)

    def stop(self):
        self.running = False
        print("Scheduler stopped")

def get_executable_directory():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    else:
        return os.path.dirname(os.path.abspath(__file__))

class BackupApp(QWidget):
    def __init__(self):
        super().__init__()

        self.source = ""
        self.destination = ""
        self.tasks = {}
        self.history = self.load_history()
        self.log = self.load_log()
        self.scheduler_thread = SchedulerThread()
        self.scheduler_thread.start()

        self.initUI()
        self.init_tray_icon()
        self.tasks = self.load_tasks()
        self.update_tasks_list()

    def initUI(self):
        layout = QVBoxLayout()

        self.tabs = QTabWidget()
        self.main_tab = QWidget()
        self.preview_tab = QWidget()
        self.tasks_tab = QWidget()
        self.history_tab = QWidget()
        self.log_tab = QWidget()

        self.init_main_tab()
        self.init_preview_tab()
        self.init_tasks_tab()
        self.init_history_tab()
        self.init_log_tab()

        self.tabs.addTab(self.main_tab, "Main")
        self.tabs.addTab(self.preview_tab, "Preview Changes")
        self.tabs.addTab(self.tasks_tab, "Tasks")
        self.tabs.addTab(self.history_tab, "History")
        self.tabs.addTab(self.log_tab, "Log")

        layout.addWidget(self.tabs)

        self.setLayout(layout)
        self.setWindowTitle("Incremental Backup Application")
        self.setGeometry(300, 300, 1000, 600)
        self.setWindowIcon(QIcon('appicon.ico'))

    def init_main_tab(self):
        layout = QVBoxLayout()
        layout.setSpacing(10)
        layout.setContentsMargins(10, 10, 10, 10)

        self.style_label = QLabel("Select Style:")
        self.style_label.setFixedHeight(30)
        layout.addWidget(self.style_label)

        self.style_combo = QComboBox()
        self.style_combo.addItems(QStyleFactory.keys())
        self.style_combo.currentIndexChanged[str].connect(self.change_style)
        layout.addWidget(self.style_combo)

        fusion_index = self.style_combo.findText("Fusion", Qt.MatchFixedString)
        if fusion_index >= 0:
            self.style_combo.setCurrentIndex(fusion_index)
            QApplication.setStyle(QStyleFactory.create("Fusion"))

        self.source_label = QLabel("Source Directory: Not set")
        self.source_label.setFixedHeight(20)
        layout.addWidget(self.source_label)

        self.source_button = QPushButton("Set Source Directory")
        self.source_button.setFixedHeight(30)
        self.source_button.clicked.connect(self.set_source)
        layout.addWidget(self.source_button)

        self.destination_label = QLabel("Destination Directory: Not set")
        self.destination_label.setFixedHeight(20)
        layout.addWidget(self.destination_label)

        self.destination_button = QPushButton("Set Destination Directory")
        self.destination_button.setFixedHeight(30)
        self.destination_button.clicked.connect(self.set_destination)
        layout.addWidget(self.destination_button)

        self.backup_button = QPushButton("Start Backup")
        self.backup_button.setFixedHeight(30)
        self.backup_button.clicked.connect(self.start_backup)
        layout.addWidget(self.backup_button)

        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(30)
        self.progress_bar.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.progress_bar)

        self.exit_button = QPushButton("Exit")
        self.exit_button.setFixedHeight(30)
        self.exit_button.clicked.connect(self.close)
        layout.addWidget(self.exit_button)

        self.main_tab.setLayout(layout)

    def change_style(self, style_name):
        QApplication.setStyle(QStyleFactory.create(style_name))

    def init_preview_tab(self):
        layout = QVBoxLayout()
        self.preview_layout = layout

        self.preview_changes_button = QPushButton("Load Preview Changes")
        self.preview_changes_button.clicked.connect(self.preview_changes)
        layout.addWidget(self.preview_changes_button)

        self.preview_tab.setLayout(layout)

    def init_tasks_tab(self):
        layout = QVBoxLayout()

        self.task_name_input = QLineEdit()
        self.task_name_input.setPlaceholderText("Enter task name")
        self.task_name_input.setFixedHeight(30)
        self.task_name_input.textChanged.connect(self.on_task_name_changed)  # Add this line
        layout.addWidget(self.task_name_input)

        self.task_source_button = QPushButton("Set Task Source Directory")
        self.task_source_button.clicked.connect(self.set_task_source)
        self.task_source_button.setFixedHeight(30)
        layout.addWidget(self.task_source_button)

        self.task_destination_button = QPushButton("Set Task Destination Directory")
        self.task_destination_button.clicked.connect(self.set_task_destination)
        self.task_destination_button.setFixedHeight(30)
        layout.addWidget(self.task_destination_button)

        self.frequency_combo = QComboBox()
        self.frequency_combo.addItems(["Once", "Daily", "Weekly"])
        self.frequency_combo.setFixedHeight(30)
        layout.addWidget(self.frequency_combo)

        self.time_edit = QTimeEdit()
        self.time_edit.setDisplayFormat("HH:mm")
        self.time_edit.setFixedHeight(30)
        layout.addWidget(self.time_edit)

        self.day_combo = QComboBox()
        self.day_combo.addItems(["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"])
        self.day_combo.setFixedHeight(30)
        layout.addWidget(self.day_combo)
        self.day_combo.setVisible(False)

        self.frequency_combo.currentIndexChanged.connect(self.update_day_combo_visibility)

        self.save_task_button = QPushButton("Save Task")
        self.save_task_button.clicked.connect(self.save_task)
        self.save_task_button.setFixedHeight(30)
        layout.addWidget(self.save_task_button)

        self.delete_task_button = QPushButton("Delete Task(s)")
        self.delete_task_button.clicked.connect(self.delete_task)
        self.delete_task_button.setFixedHeight(30)
        layout.addWidget(self.delete_task_button)

        self.tasks_list = QListWidget()
        self.tasks_list.setSelectionMode(QListWidget.SingleSelection)
        self.tasks_list.itemClicked.connect(self.load_task)
        self.tasks_list.setFixedHeight(130)
        layout.addWidget(self.tasks_list)

        self.update_tasks_list()

        self.tasks_tab.setLayout(layout)

    def init_history_tab(self):
        layout = QHBoxLayout()
        splitter = QSplitter(Qt.Horizontal)

        self.history_list = QListWidget()
        self.history_list.itemClicked.connect(self.display_history)
        self.update_history_list()

        splitter.addWidget(self.history_list)

        self.figure = plt.figure()
        self.canvas = FigureCanvas(self.figure)

        splitter.addWidget(self.canvas)

        layout.addWidget(splitter)
        self.history_tab.setLayout(layout)

    def init_log_tab(self):
        layout = QHBoxLayout()
        splitter = QSplitter(Qt.Horizontal)

        self.log_list = QListWidget()
        self.log_list.itemClicked.connect(self.display_log)
        self.update_log_list()

        splitter.addWidget(self.log_list)

        self.log_detail = QListWidget()

        splitter.addWidget(self.log_detail)

        layout.addWidget(splitter)
        self.log_tab.setLayout(layout)

    def init_tray_icon(self):
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(QIcon('appicon.ico'))

        tray_menu = QMenu()

        restore_action = tray_menu.addAction("Restore")
        restore_action.triggered.connect(self.show)

        exit_action = tray_menu.addAction("Exit")
        exit_action.triggered.connect(QApplication.instance().quit)

        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self.on_tray_icon_activated)  # Add this line
        self.tray_icon.show()

    def closeEvent(self, event):
        event.ignore()
        self.hide()
        self.tray_icon.showMessage(
            "BackupBanana",
            "The application is still running for scheduled backups.",
            QSystemTrayIcon.Information,
            2000
        )

    def on_tray_icon_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self.show()

    def update_day_combo_visibility(self, index):
        self.day_combo.setVisible(index == 2)

    def on_task_name_changed(self, text):
        if text:
            self.save_task_button.setEnabled(True)
        else:
            self.save_task_button.setEnabled(False)

    def set_task_source(self):
        self.task_source = QFileDialog.getExistingDirectory(self, "Select Task Source Directory")

    def set_task_destination(self):
        self.task_destination = QFileDialog.getExistingDirectory(self, "Select Task Destination Directory")

    def save_task(self):
        task_name = self.task_name_input.text().strip()
        if not task_name:
            QMessageBox.critical(self, "Error", "Task name must be set.")
            return

        if not self.task_source or not self.task_destination:
            QMessageBox.critical(self, "Error", "Source and destination must be set.")
            return

        schedule_info = {
            "frequency": self.frequency_combo.currentText(),
            "time": self.time_edit.time().toString("HH:mm"),
            "day": self.day_combo.currentText() if self.frequency_combo.currentIndex() == 2 else None
        }

        new_task = {
            "source": self.task_source,
            "destination": self.task_destination,
            "schedule": schedule_info
        }

        if task_name in self.tasks:
            self.tasks[task_name] = new_task
        else:
            old_task_name = next((name for name, info in self.tasks.items() if info == new_task), None)
            if old_task_name:
                del self.tasks[old_task_name]
            self.tasks[task_name] = new_task

        self.save_tasks()
        self.update_tasks_list()
        QMessageBox.information(self, "Task Saved", "Task has been saved successfully.")
        self.schedule_task(task_name)

    def delete_task(self):
        selected_items = self.tasks_list.selectedItems()
        if not selected_items:
            QMessageBox.critical(self, "Error", "No task selected.")
            return

        for item in selected_items:
            task_name = item.text().split(' - ')[0]
            if task_name in self.tasks:
                del self.tasks[task_name]

        self.save_tasks()
        self.update_tasks_list()
        QMessageBox.information(self, "Task Deleted", "Selected task(s) have been deleted successfully.")

    def load_tasks(self):
        tasks_file = os.path.join(get_executable_directory(), "tasks.json")
        if os.path.exists(tasks_file):
            with open(tasks_file, "r") as f:
                tasks = json.load(f)
                for task_name, task_info in tasks.items():
                    if task_info["schedule"]["frequency"] != "Once":
                        try:
                            self.schedule_task(task_name)
                        except KeyError as e:
                            print(f"Error scheduling task: {task_name}. Missing key: {str(e)}")
                        except Exception as e:
                            print(f"Unexpected error scheduling task: {task_name}. Error: {str(e)}")
                return tasks
        return {}

    def update_tasks_list(self):
        self.tasks_list.clear()
        for task_name, task_info in self.tasks.items():
            schedule_info = task_info['schedule']
            frequency = schedule_info['frequency']
            time = schedule_info['time']
            day = schedule_info['day']
            if frequency == 'Weekly':
                schedule_text = f"{frequency} at {time} on {day}"
            else:
                schedule_text = f"{frequency} at {time}"

            item_text = f"{task_name} - Source: {task_info['source']} - Destination: {task_info['destination']} - Schedule: {schedule_text}"
            item = QListWidgetItem(item_text)
            self.tasks_list.addItem(item)

    def save_tasks(self):
        tasks_file = os.path.join(get_executable_directory(), "tasks.json")
        with open(tasks_file, "w") as f:
            json.dump(self.tasks, f)

    def reset_preview_layout(self):
        for i in reversed(range(self.preview_layout.count())):
            widget = self.preview_layout.itemAt(i).widget()
            if widget is not None:
                widget.setParent(None)

        self.preview_changes_button = QPushButton("Load Preview Changes")
        self.preview_changes_button.clicked.connect(self.preview_changes)
        self.preview_layout.addWidget(self.preview_changes_button)
        self.preview_changes_button.setFixedHeight(40)

    def load_task(self, item):
        self.reset_preview_layout()

        item_text = item.text()
        task_name = item_text.split(' - ')[0]
        task = self.tasks[task_name]

        self.source = task["source"]
        self.destination = task["destination"]
        self.source_label.setText(f"Source Directory: {self.source}")
        self.destination_label.setText(f"Destination Directory: {self.destination}")

        self.task_name_input.setText(task_name)
        schedule_info = task["schedule"]
        self.frequency_combo.setCurrentText(schedule_info["frequency"])
        self.time_edit.setTime(QTime.fromString(schedule_info["time"], "HH:mm"))

        if schedule_info["frequency"] == "Weekly":
            self.day_combo.setCurrentText(schedule_info["day"])
            self.day_combo.setVisible(True)
        else:
            self.day_combo.setVisible(False)

        self.save_task_button.setEnabled(False)

    def schedule_task(self, task_name):
        print(f"Scheduling task: {task_name}")
        if task_name not in self.tasks:
            raise KeyError(f"Task '{task_name}' not found in tasks dictionary")

        task = self.tasks[task_name]
        schedule_info = task["schedule"]
        time_str = schedule_info["time"]

        if schedule_info["frequency"] == "Once":
            print(f"Task {task_name} is set to run once.")
            return

        if schedule_info["frequency"] == "Daily":
            self.scheduler_thread.scheduler.every().day.at(time_str).do(self.run_scheduled_backup, task_name)
            print(f"Task {task_name} scheduled daily at {time_str}")
        elif schedule_info["frequency"] == "Weekly":
            day = schedule_info["day"].lower()
            day_method = getattr(self.scheduler_thread.scheduler.every(), day)
            day_method.at(time_str).do(self.run_scheduled_backup, task_name)
            print(f"Task {task_name} scheduled weekly on {day.capitalize()} at {time_str}")

    def run_scheduled_backup(self, task_name):
        print(f"Running scheduled backup for task: {task_name}")
        task = self.tasks.get(task_name)
        if not task:
            print(f"Task {task_name} not found.")
            return
        print(f"Task details: {task}")
        self.source = task["source"]
        self.destination = task["destination"]
        self.start_backup()

    def set_source(self):
        self.source = QFileDialog.getExistingDirectory(self, "Select Source Directory")
        self.source_label.setText(f"Source Directory: {self.source}")
        self.reset_preview_layout()

    def set_destination(self):
        self.destination = QFileDialog.getExistingDirectory(self, "Select Destination Directory")
        self.destination_label.setText(f"Destination Directory: {self.destination}")
        self.reset_preview_layout()

    def preview_changes(self):
        if not self.source or not self.destination:
            QMessageBox.critical(self, "Error", "Both source and destination directories must be set.")
            return

        for i in reversed(range(self.preview_layout.count())):
            widget = self.preview_layout.itemAt(i).widget()
            if widget is not None:
                widget.setParent(None)

        new_files, modified_files, total_size = self.get_changes()

        size_label = QLabel(f"Total size to be copied: {total_size / 1024:.2f} KB")
        self.preview_layout.addWidget(size_label)

        lists_layout = QHBoxLayout()

        new_files_list = QListWidget()
        new_files_list.addItems(new_files)
        modified_files_list = QListWidget()
        modified_files_list.addItems(modified_files)

        lists_layout.addWidget(QLabel("Files to be copied"))
        lists_layout.addWidget(new_files_list)
        lists_layout.addWidget(QLabel("Files to be modified"))
        lists_layout.addWidget(modified_files_list)

        self.preview_layout.addLayout(lists_layout)

    def is_destination_reachable(self):
        return os.path.exists(self.destination)

    def handle_backup_error(self, errors):
        QMessageBox.critical(self, "Backup Error", "\n".join(errors))
        self.tray_icon.showMessage(
            "BackupBanana",
            "Backup failed. Please check the error log.",
            QSystemTrayIcon.Critical,
            2000
        )

    def start_backup(self):
        if not self.source or not self.destination:
            QMessageBox.critical(self, "Error", "Both source and destination directories must be set.")
            return

        if not self.is_destination_reachable():
            self.tray_icon.showMessage(
                "BackupBanana",
                "Destination directory is not reachable. Please check the connection.",
                QSystemTrayIcon.Warning,
                2000
            )
            return

        new_files, modified_files, _ = self.get_changes()
        if not new_files and not modified_files:
            self.tray_icon.showMessage(
                "BackupBanana",
                "No changes detected.",
                QSystemTrayIcon.Information,
                2000
            )
            return

        self.progress_bar.setValue(0)
        self.thread = BackupThread(self.source, self.destination)
        self.thread.progress_update.connect(self.progress_bar.setValue)
        self.thread.backup_finished.connect(self.record_history)
        self.thread.error_occurred.connect(self.handle_backup_error)
        self.thread.start()

    def backup_finished(self):
        self.tray_icon.showMessage(
            "BackupBanana",
            "Backup completed successfully.",
            QSystemTrayIcon.Information,
            2000
        )

    def record_history(self, result):
        self.history.append(result)
        self.save_history()
        self.update_history_list()

        if result['errors']:
            self.log.append(result)
            self.save_log()
            self.update_log_list()

        if result['copied_files'] == 0 and result['modified_files'] == 0:
            self.tray_icon.showMessage(
                "BackupBanana",
                "No changes detected.",
                QSystemTrayIcon.Information,
                2000
            )
        else:
            self.tray_icon.showMessage(
                "BackupBanana",
                "Backup completed successfully.",
                QSystemTrayIcon.Information,
                2000
            )

    def load_log(self):
        log_file = os.path.join(get_executable_directory(), "log.json")
        if os.path.exists(log_file):
            with open(log_file, "r") as f:
                return json.load(f)
        return []

    def save_log(self):
        log_file = os.path.join(get_executable_directory(), "log.json")
        with open(log_file, "w") as f:
            json.dump(self.log, f)

    def update_log_list(self):
        self.log_list.clear()
        for record in self.log:
            item = QListWidgetItem(record["date"])
            self.log_list.addItem(item)

    def display_log(self, item):
        selected_date = item.text()
        record = next((rec for rec in self.log if rec["date"] == selected_date), None)
        if record:
            self.log_detail.clear()
            self.log_detail.addItems(record["errors"])

    def update_history_list(self):
        self.history_list.clear()
        for record in self.history:
            item = QListWidgetItem(record["date"])
            self.history_list.addItem(item)

    def display_history(self, item):
        selected_date = item.text()
        record = next((rec for rec in self.history if rec["date"] == selected_date), None)
        if record:
            self.plot_history(record)

    def plot_history(self, record):
        self.figure.clear()
        ax = self.figure.add_subplot(111)
        labels = ["Copied Files", "Modified Files", "Copied Folders", "Modified Folders"]
        sizes = [record["copied_files"], record["modified_files"], record["copied_folders"], record["modified_folders"]]
        ax.bar(labels, sizes)
        ax.set_ylabel("Number of Items")
        title = f"Backup on {record['date']}"
        subtitle = f"Source: {self.source}\nDestination: {self.destination}"
        ax.set_title(f"{title}\n{subtitle}")
        self.canvas.draw()

    def get_changes(self):
        new_files = []
        modified_files = []
        total_size = 0
        for root, dirs, files in os.walk(self.source):
            relative_path = os.path.relpath(root, self.source)
            dest_path = os.path.join(self.destination, relative_path)
            if not os.path.exists(dest_path):
                new_files.append(f"New folder: {dest_path}")
            for file in files:
                source_file = os.path.join(root, file)
                dest_file = os.path.join(dest_path, file)
                file_size = os.path.getsize(source_file)
                if not os.path.exists(dest_file):
                    new_files.append(dest_file)
                    total_size += file_size
                elif os.path.getmtime(source_file) > os.path.getmtime(dest_file):
                    modified_files.append(dest_file)
                    total_size += file_size
        return new_files, modified_files, total_size

    def save_history(self):
        history_file = os.path.join(get_executable_directory(), "history.json")
        with open(history_file, "w") as f:
            json.dump(self.history, f)

    def load_history(self):
        history_file = os.path.join(get_executable_directory(), "history.json")
        if os.path.exists(history_file):
            with open(history_file, "r") as f:
                return json.load(f)
        return []

if __name__ == "__main__":
    app = QApplication([])
    app.setStyle(QStyleFactory.create("Fusion"))
    window = BackupApp()
    window.show()
    app.exec_()
