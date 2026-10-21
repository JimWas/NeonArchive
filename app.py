"""NEON ARCHIVE — desktop website mirror."""
import random
import sys
import threading
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QThread, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QFont, QFontDatabase, QPainter
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QDoubleSpinBox, QFileDialog, QFrame, QGridLayout,
    QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox, QProgressBar,
    QPushButton, QSpinBox, QTextEdit, QVBoxLayout, QWidget,
)

from scraper import Mirror, Options


class Matrix(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        rng = random.Random(42)
        self.columns = [(x, rng.randint(-600, 800), rng.randint(1, 4)) for x in range(0, 2400, 22)]
        self.tick = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.advance)
        self.timer.start(90)

    def advance(self):
        self.tick += 1
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setFont(QFont('Menlo', 10))
        chars = '01アイウエオカキクケコ∆+<>/'
        for x, start, speed in self.columns:
            y = (start + self.tick * speed) % (self.height() + 300) - 150
            for j in range(12):
                painter.setPen(QColor(24, 255, 174, max(0, 34 - j * 3)))
                painter.drawText(x, y - j * 17, chars[(x + j + self.tick // 6) % len(chars)])


class Worker(QThread):
    update = Signal(str, object)
    finished_report = Signal(object)
    failed = Signal(str)

    def __init__(self, options):
        super().__init__()
        self.options = options
        self.cancel_event = threading.Event()

    def run(self):
        try:
            report = Mirror(self.options, self.update.emit, self.cancel_event).run()
            self.finished_report.emit(report)
        except Exception as exc:
            self.failed.emit(str(exc))


class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.worker = None
        self.last_output = None
        self.setWindowTitle('NEON ARCHIVE / Website Recovery System')
        self.resize(1180, 880)
        self.setMinimumSize(920, 760)
        font_path = Path(__file__).with_name('Nasalization.otf')
        font_id = QFontDatabase.addApplicationFont(str(font_path))
        families = QFontDatabase.applicationFontFamilies(font_id)
        self.display_font = families[0] if families else 'Arial'
        root = QWidget()
        self.setCentralWidget(root)
        self.matrix = Matrix(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(36, 28, 36, 26)
        layout.setSpacing(18)
        top = QHBoxLayout()
        top.addWidget(self.label('N A  /  SYSTEMS DIVISION', 'eyebrow'))
        top.addStretch()
        self.status = self.label('●  SYSTEM READY', 'status')
        top.addWidget(self.status)
        layout.addLayout(top)
        title = self.label('NEON ARCHIVE', 'title')
        title.setFont(QFont(self.display_font, 36))
        layout.addWidget(title)
        layout.addWidget(self.label('WEBSITE RECOVERY SYSTEM    /    LOCAL MIRROR PROTOCOL 01', 'subtitle'))
        intro = self.label('Capture the web. Keep a local universe.', 'intro')
        layout.addWidget(intro)
        panel = QFrame()
        panel.setObjectName('panel')
        form = QVBoxLayout(panel)
        form.setContentsMargins(24, 20, 24, 22)
        form.setSpacing(12)
        form.addWidget(self.label('01  /  TARGET COORDINATES', 'section'))
        self.url = QLineEdit()
        self.url.setPlaceholderText('https://example.com')
        self.url.setAccessibleName('Website URL')
        form.addWidget(self.url)
        output_row = QHBoxLayout()
        self.output = QLineEdit(str(Path.home() / 'Downloads' / 'Neon Archives'))
        self.output.setAccessibleName('Download destination')
        browse = QPushButton('BROWSE')
        browse.clicked.connect(self.browse)
        output_row.addWidget(self.output, 1)
        output_row.addWidget(browse)
        form.addWidget(self.label('ARCHIVE DESTINATION  /  A NEW FOLDER IS CREATED FOR EACH RUN', 'small'))
        form.addLayout(output_row)
        controls = QHBoxLayout()
        self.limit = QSpinBox()
        self.limit.setRange(1, 100000)
        self.limit.setValue(500)
        self.limit.setSuffix(' pages')
        self.limit.setAccessibleName('Maximum pages')
        self.delay = QDoubleSpinBox()
        self.delay.setRange(0, 60)
        self.delay.setSingleStep(0.25)
        self.delay.setValue(0.25)
        self.delay.setSuffix(' sec')
        self.delay.setAccessibleName('Delay between requests')
        controls.addWidget(self.label('PAGE LIMIT', 'small'))
        controls.addWidget(self.limit)
        controls.addSpacing(20)
        controls.addWidget(self.label('REQUEST DELAY', 'small'))
        controls.addWidget(self.delay)
        controls.addStretch()
        form.addLayout(controls)
        checks = QHBoxLayout()
        self.robots = QCheckBox('Respect robots.txt')
        self.robots.setChecked(True)
        self.external = QCheckBox('Include CDN / external assets')
        self.external.setChecked(True)
        checks.addWidget(self.robots)
        checks.addWidget(self.external)
        checks.addStretch()
        form.addLayout(checks)
        actions = QHBoxLayout()
        self.start_button = QPushButton('▶  INITIATE ARCHIVE')
        self.start_button.setObjectName('primary')
        self.start_button.clicked.connect(self.start)
        self.stop_button = QPushButton('■  ABORT')
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.stop)
        self.open_button = QPushButton('↗  OPEN OFFLINE SITE')
        self.open_button.setEnabled(False)
        self.open_button.clicked.connect(self.open_site)
        actions.addWidget(self.start_button, 2)
        actions.addWidget(self.stop_button, 1)
        actions.addWidget(self.open_button, 2)
        form.addLayout(actions)
        layout.addWidget(panel)
        cards = QHBoxLayout()
        self.counters = {}
        for key, name in [('pages', 'PAGES CAPTURED'), ('assets', 'SUPPORT FILES'), ('bytes', 'DATA TRANSFERRED'), ('errors', 'SKIPPED / ERRORS')]:
            card = QFrame()
            card.setObjectName('card')
            box = QVBoxLayout(card)
            box.setContentsMargins(18, 14, 18, 14)
            value = self.label('0 MB' if key == 'bytes' else '000', 'counter')
            value.setFont(QFont(self.display_font, 24))
            box.addWidget(value)
            box.addWidget(self.label(name, 'small'))
            self.counters[key] = value
            cards.addWidget(card)
        layout.addLayout(cards)
        log_heading = QHBoxLayout()
        log_heading.addWidget(self.label('02  /  MISSION TELEMETRY', 'section'))
        log_heading.addStretch()
        self.queue_label = self.label('AWAITING TARGET', 'small')
        log_heading.addWidget(self.queue_label)
        layout.addLayout(log_heading)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(3)
        layout.addWidget(self.progress)
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.document().setMaximumBlockCount(1500)
        self.log.setMinimumHeight(130)
        self.log.setFont(QFont('Menlo', 11))
        layout.addWidget(self.log, 1)
        self.log_line('NEON ARCHIVE online. Enter a target URL to begin.')
        layout.addWidget(self.label('SAME-HOST CRAWL  •  OFFLINE LINK REPAIR  •  HTML / CSS / JS / MEDIA    //    PUBLIC WEB FILES ONLY', 'footer'))
        self.inputs = [self.url, self.output, browse, self.limit, self.delay, self.robots, self.external]
        self.setStyleSheet('''
            QMainWindow, QWidget { background: #070d16; color: #d8e7f0; font-size: 12px; }
            QLabel { background: transparent; }
            QLabel#eyebrow, QLabel#subtitle { color: #6c8499; letter-spacing: 3px; }
            QLabel#title { color: #e0fbff; font-size: 42px; }
            QLabel#intro { color: #9eafc0; font-size: 16px; }
            QLabel#status { color: #54ffbb; letter-spacing: 2px; }
            QLabel#section { color: #43dbe8; letter-spacing: 2px; font-weight: bold; }
            QLabel#small { color: #8fa4b8; font-size: 10px; letter-spacing: 1px; }
            QLabel#footer { color: #678096; font-size: 9px; letter-spacing: 1px; }
            QLabel#counter { color: #58efcf; font-size: 26px; }
            QFrame#panel, QFrame#card { background: rgba(13, 25, 39, 235); border: 1px solid #243c50; border-radius: 8px; }
            QLineEdit, QSpinBox, QDoubleSpinBox { background: #080f1c; border: 1px solid #30485e; border-radius: 4px; padding: 10px; color: #e4f4fa; selection-background-color: #196c76; }
            QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus { border-color: #41ded7; }
            QPushButton { background: #142738; border: 1px solid #36516b; padding: 12px 15px; border-radius: 4px; color: #9ec9df; font-weight: bold; letter-spacing: 1px; }
            QPushButton:hover { border-color: #43e4d4; color: #ecffff; background: #1b3849; }
            QPushButton#primary { background: #45ead0; color: #061722; border-color: #45ead0; }
            QPushButton#primary:hover { background: #8affdf; }
            QPushButton:disabled { color: #4c6276; background: #101c29; border-color: #233447; }
            QCheckBox { background: transparent; color: #a9bdce; spacing: 8px; }
            QCheckBox::indicator { width: 15px; height: 15px; border: 1px solid #486178; border-radius: 2px; background: #0a1520; }
            QCheckBox::indicator:checked { background: #45ead0; border-color: #45ead0; }
            QTextEdit { background: rgba(5, 12, 22, 235); border: 1px solid #23384e; border-radius: 5px; color: #79c6bd; padding: 12px; }
            QProgressBar { border: 0; background: #172b3d; }
            QProgressBar::chunk { background: #ef8d55; }
            QToolTip { color: #e0fbff; background: #142738; border: 1px solid #43e4d4; }
        ''')

    def label(self, text, name):
        label = QLabel(text)
        label.setObjectName(name)
        return label

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'matrix'):
            self.matrix.setGeometry(self.centralWidget().rect())
            self.matrix.lower()

    def browse(self):
        path = QFileDialog.getExistingDirectory(self, 'Choose archive destination', self.output.text())
        if path:
            self.output.setText(path)

    def log_line(self, text):
        self.log.append('')
        cursor = self.log.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        cursor.insertText(f'[{datetime.now():%H:%M:%S}]  {text}')
        self.log.setTextCursor(cursor)
        self.log.ensureCursorVisible()

    def start(self):
        raw = self.url.text().strip()
        if '://' not in raw:
            raw = 'https://' + raw
        normalized = Mirror.normalize(raw)
        if not normalized:
            QMessageBox.warning(self, 'Invalid target', 'Enter a valid website URL, such as https://example.com.')
            return
        if not self.output.text().strip():
            QMessageBox.warning(self, 'Choose a destination', 'Choose where to save the archive.')
            return
        from urllib.parse import urlsplit
        host = urlsplit(normalized).hostname
        folder = Path(self.output.text()).expanduser() / f'{host}-{datetime.now():%Y%m%d-%H%M%S-%f}'
        self.last_output = folder
        self.url.setText(normalized)
        options = Options(normalized, folder, self.limit.value(), self.delay.value(), self.external.isChecked(), self.robots.isChecked())
        self.worker = Worker(options)
        self.worker.update.connect(self.on_update)
        self.worker.finished_report.connect(self.completed)
        self.worker.failed.connect(self.failed)
        self.worker.finished.connect(self.thread_finished)
        for widget in self.inputs:
            widget.setEnabled(False)
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.open_button.setEnabled(False)
        self.progress.setRange(0, 0)
        self.status.setText('●  ARCHIVING')
        self.on_update('stats', dict(pages=0, assets=0, bytes=0, errors=0, pending=1))
        self.log_line(f'MISSION START  {normalized}')
        self.log_line(f'DESTINATION    {folder}')
        self.worker.start()

    def on_update(self, kind, payload):
        if kind == 'log':
            self.log_line(payload)
        elif kind == 'stats':
            for key, label in self.counters.items():
                label.setText(f'{payload[key] / 1048576:.1f} MB' if key == 'bytes' else f'{payload[key]:03d}')
            self.queue_label.setText(f'{payload["pending"]} REQUESTS QUEUED')

    def stop(self):
        if self.worker:
            self.worker.cancel_event.set()
            self.stop_button.setEnabled(False)
            self.status.setText('●  FINALIZING')
            self.log_line('Cancellation requested. Finishing the current request and repairing saved links…')

    def thread_finished(self):
        for widget in self.inputs:
            widget.setEnabled(True)
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.progress.setRange(0, 1)
        self.progress.setValue(1)
        self.worker.deleteLater()
        self.worker = None

    def completed(self, report):
        self.status.setText('●  CANCELLED' if report['cancelled'] else '●  ARCHIVE COMPLETE' if report['pages'] else '●  NO PAGES SAVED')
        self.queue_label.setText('PARTIAL ARCHIVE' if report['cancelled'] else 'MISSION FINISHED')
        self.open_button.setEnabled((self.last_output / 'index.html').exists())
        self.log_line(f'FINISHED  {report["pages"]} pages / {report["assets"]} files / {len(report["errors"])} skipped. Report: manifest.json')

    def failed(self, message):
        self.status.setText('●  MISSION FAILED')
        self.queue_label.setText('CHECK TELEMETRY')
        self.log_line(f'ERROR  {message}')
        QMessageBox.warning(self, 'Archive failed', message)

    def open_site(self):
        if self.last_output:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.last_output / 'index.html')))

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.stop()
            self.log_line('Please wait for finalization, then close the window.')
            event.ignore()
        else:
            event.accept()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    window = Window()
    window.show()
    sys.exit(app.exec())
