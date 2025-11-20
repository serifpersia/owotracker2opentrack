import sys
import socket
import struct
import time
import math

from PyQt5.QtWidgets import QApplication, QWidget, QLabel, QGridLayout, QPushButton, QLineEdit, QComboBox, QCheckBox, QHBoxLayout, QVBoxLayout, QGroupBox, QFormLayout
from PyQt5.QtCore import QThread, QObject, QTimer, QMutex, Qt
from PyQt5.QtOpenGL import QGLWidget
from OpenGL.GL import *
from OpenGL.GLU import *

LISTEN_IP = "0.0.0.0"
LISTEN_PORT = 6969
DEFAULT_OPENTRACK_IP = "127.0.0.1"
DEFAULT_OPENTRACK_PORT = 4242
HEARTBEAT_INTERVAL_S = 2.0
TRACKER_TIMEOUT_S = 5.0
UI_REFRESH_RATE_MS = 1000 // 60
DEGREE_CHANGE_THRESHOLD = 0.1

class OpenGLWidget(QGLWidget):
    def __init__(self, parent=None):
        super(OpenGLWidget, self).__init__(parent)
        self.yaw, self.pitch, self.roll = 0, 0, 0

    def initializeGL(self):
        glClearColor(0.17, 0.17, 0.17, 1.0)
        glEnable(GL_DEPTH_TEST)

    def resizeGL(self, w, h):
        glViewport(0, 0, w, h)
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        gluPerspective(45, w / h, 0.1, 50.0)
        glMatrixMode(GL_MODELVIEW)

    def paintGL(self):
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        glLoadIdentity()
        glTranslatef(0.0, 0.0, -5.0)
        glRotatef(self.yaw, 0.0, 1.0, 0.0)
        glRotatef(self.pitch, 1.0, 0.0, 0.0)
        glRotatef(self.roll, 0.0, 0.0, 1.0)
        glBegin(GL_LINES)
        glColor3f(1.0, 0.0, 0.0)
        glVertex3f(0.0, 0.0, 0.0)
        glVertex3f(1.0, 0.0, 0.0)
        glColor3f(0.0, 1.0, 0.0)
        glVertex3f(0.0, 0.0, 0.0)
        glVertex3f(0.0, 1.0, 0.0)
        glColor3f(0.0, 0.0, 1.0)
        glVertex3f(0.0, 0.0, 0.0)
        glVertex3f(0.0, 0.0, 1.0)
        glEnd()

        glPointSize(10.0)
        glBegin(GL_POINTS)
        glColor3f(1.0, 1.0, 1.0)
        glVertex3f(0.0, 0.0, 1.0)
        glEnd()

    def update_rotation(self, yaw, pitch, roll):
        self.yaw, self.pitch, self.roll = -yaw, -pitch, -roll
        self.update()

def quat_to_euler(x, y, z, w):
    siny_cosp = 2 * (w * z + x * y)
    cosy_cosp = 1 - 2 * (y * y + z * z)
    yaw = math.degrees(math.atan2(siny_cosp, cosy_cosp))
    sinp = 2 * (w * y - z * x)
    pitch = math.degrees(math.asin(max(-1, min(1, sinp))))
    sinr_cosp = 2 * (w * x + y * z)
    cosr_cosp = 1 - 2 * (x * x + y * y)
    roll = math.degrees(math.atan2(sinr_cosp, cosr_cosp))
    return yaw, pitch, roll

class UdpWorker(QObject):
    def __init__(self, trackers_dict, lock):
        super().__init__()
        self.running = True
        self.forwarding = False
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock_out = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.trackers = trackers_dict
        self.lock = lock
        self.active_addrs = set()
        self.opentrack_ip = DEFAULT_OPENTRACK_IP
        self.opentrack_port = DEFAULT_OPENTRACK_PORT
        self.mapping = {
            'yaw': {'source': 'yaw', 'invert': False},
            'pitch': {'source': 'pitch', 'invert': False},
            'roll': {'source': 'roll', 'invert': False}
        }
        self.yaw_offset, self.pitch_offset, self.roll_offset = 0.0, 0.0, 0.0
        self.last_packet_ids = {}

    def run(self):
        self.sock.bind((LISTEN_IP, LISTEN_PORT))
        self.sock.settimeout(0.1)
        last_heartbeat_time = 0
        while self.running:
            current_time = time.time()
            try:
                data, addr = self.sock.recvfrom(1024)
                if addr not in self.active_addrs:
                    self.active_addrs.add(addr)
                self.lock.lock()
                try:
                    if addr not in self.trackers:
                        self.trackers[addr] = {}
                        self.last_packet_ids[addr] = -1
                    self.trackers[addr]['last_seen'] = current_time
                    if len(data) >= 12:
                        pkt_type = struct.unpack(">I", data[:4])[0]
                        if pkt_type == 3:
                            self.sock.sendto(b'\x03Hey OVR =D 5\0', addr)
                        elif pkt_type == 1 and len(data) >= 28:
                            packet_id = struct.unpack(">q", data[4:12])[0]
                            if packet_id <= self.last_packet_ids.get(addr, -1):
                                continue
                            self.last_packet_ids[addr] = packet_id
                            self.trackers[addr]['rotation'] = struct.unpack(">4f", data[12:28])
                        elif pkt_type == 12 and len(data) >= 16:
                            self.trackers[addr]['battery'] = f"{struct.unpack('>f', data[12:16])[0] * 100:.1f}%"
                    
                    if 'rotation' in self.trackers.get(addr, {}):
                        x, y, z, w = self.trackers[addr]['rotation']
                        phone_yaw, phone_pitch, phone_roll = quat_to_euler(x, y, z, w)
                        raw_yaw = -phone_yaw
                        raw_pitch = -phone_roll
                        raw_roll = phone_pitch
                        self.trackers[addr]['raw_angles'] = (raw_yaw, raw_pitch, raw_roll)
                        
                        final_yaw = (raw_yaw - self.yaw_offset + 180) % 360 - 180
                        final_pitch = raw_pitch - self.pitch_offset
                        final_roll = raw_roll - self.roll_offset
                        self.trackers[addr]['final_angles'] = (final_yaw, final_pitch, final_roll)

                        internal_angles = {'yaw': final_yaw, 'pitch': final_pitch, 'roll': final_roll}
                        output_angles = {}
                        for out_axis in ['yaw', 'pitch', 'roll']:
                            source_axis = self.mapping[out_axis]['source']
                            value = internal_angles.get(source_axis, 0.0) if source_axis != 'disabled' else 0.0
                            if self.mapping[out_axis]['invert']:
                                value *= -1
                            output_angles[out_axis] = value
                        self.trackers[addr]['output_angles'] = (output_angles['yaw'], output_angles['pitch'], output_angles['roll'])

                        if self.forwarding:
                            opentrack_packet = struct.pack("<6d", 0.0, 0.0, 0.0, output_angles['yaw'], output_angles['pitch'], output_angles['roll'])
                            self.sock_out.sendto(opentrack_packet, (self.opentrack_ip, self.opentrack_port))
                finally:
                    self.lock.unlock()
            except (socket.timeout, socket.error):
                pass
            if (current_time - last_heartbeat_time) > HEARTBEAT_INTERVAL_S:
                heartbeat_packet = struct.pack('>I', 1)
                disconnected_trackers = []
                self.lock.lock()
                try:
                    for t_addr, t_data in self.trackers.items():
                        if current_time - t_data.get('last_seen', 0) > TRACKER_TIMEOUT_S:
                            disconnected_trackers.append(t_addr)
                        else:
                            self.sock.sendto(heartbeat_packet, t_addr)
                    for t_addr in disconnected_trackers:
                        del self.trackers[t_addr]
                        self.active_addrs.discard(t_addr)
                        if t_addr in self.last_packet_ids:
                            del self.last_packet_ids[t_addr]
                finally:
                    self.lock.unlock()
                last_heartbeat_time = current_time
        self.sock.close()
        self.sock_out.close()

    def zero_tracker(self):
        self.lock.lock()
        try:
            if self.trackers:
                addr = list(self.trackers.keys())[0]
                if 'raw_angles' in self.trackers[addr]:
                    self.yaw_offset, self.pitch_offset, self.roll_offset = self.trackers[addr]['raw_angles']
        finally:
            self.lock.unlock()

    def stop(self):
        self.running = False
        self.sock.close()

    def set_forwarding(self, state):
        self.forwarding = state

    def set_opentrack_port(self, port):
        try:
            self.opentrack_port = int(port)
        except (ValueError, TypeError):
            self.opentrack_port = DEFAULT_OPENTRACK_PORT

    def set_mapping(self, out_axis, source, invert):
        if out_axis in self.mapping:
            self.mapping[out_axis] = {'source': source, 'invert': invert}

class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("oWoTrack Visual Bridge")
        self.setGeometry(100, 100, 850, 420)
        self.setStyleSheet("""
            QWidget { background-color: #2b2b2b; color: #f0f0f0; font-size: 14px; }
            QGroupBox { font-weight: bold; border: 1px solid #444; border-radius: 5px; margin-top: 10px; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px 0 5px; }
            QLabel { padding: 4px; }
            QPushButton { padding: 8px; border: 1px solid #555; border-radius: 4px; font-weight: bold; }
            QLineEdit, QComboBox { border: 1px solid #555; border-radius: 4px; padding: 4px; background-color: #3c3f41; }
            QComboBox::drop-down { border: none; }
        """)
        
        self.lock = QMutex()
        self.trackers = {}
        self.thread = QThread()
        self.worker = UdpWorker(self.trackers, self.lock)
        self.worker.moveToThread(self.thread)

        self.main_layout = QHBoxLayout(self)
        self.main_layout.setContentsMargins(10, 10, 10, 10)
        self.controls_widget = QWidget()
        self.controls_layout = QVBoxLayout(self.controls_widget)
        self.controls_layout.setSpacing(10)
        self.controls_layout.setContentsMargins(0, 0, 0, 0)
        self.opengl_widget = OpenGLWidget()
        self.main_layout.addWidget(self.controls_widget, 1)
        self.main_layout.addWidget(self.opengl_widget, 1)
        self.displayed_tracker_addr = None
        self.last_ui_angles = {'yaw': None, 'pitch': None, 'roll': None}
        self.status_label = QLabel("Waiting for a tracker to connect...")
        self.status_label.setStyleSheet("font-style: italic; color: #888;")
        self.controls_layout.addWidget(self.status_label)
        self._setup_ui_groups()
        self.reset_ui_to_waiting()
        
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_ui)
        self.timer.start(UI_REFRESH_RATE_MS)
        self.thread.started.connect(self.worker.run)
        self.thread.start()

    def _setup_ui_groups(self):
        self.tracker_status_group = QGroupBox("Tracker Status")
        status_layout = QFormLayout(self.tracker_status_group)
        self.info_widgets = {'name': QLabel("..."), 'ip': QLabel("..."), 'battery': QLabel("...")}
        status_layout.addRow("<b>Name:</b>", self.info_widgets['name'])
        status_layout.addRow("<b>IP Address:</b>", self.info_widgets['ip'])
        status_layout.addRow("<b>Battery:</b>", self.info_widgets['battery'])
        self.controls_layout.addWidget(self.tracker_status_group)
        self.raw_data_group = QGroupBox("Internal Sensor Data")
        raw_data_layout = QFormLayout(self.raw_data_group)
        self.raw_data_widgets = {'yaw': QLabel("..."), 'pitch': QLabel("..."), 'roll': QLabel("...")}
        raw_data_layout.addRow("<b>Raw Yaw:</b>", self.raw_data_widgets['yaw'])
        raw_data_layout.addRow("<b>Raw Pitch:</b>", self.raw_data_widgets['pitch'])
        raw_data_layout.addRow("<b>Raw Roll:</b>", self.raw_data_widgets['roll'])
        self.controls_layout.addWidget(self.raw_data_group)

        self.opentrack_output_group = QGroupBox("OpenTrack Output")
        opentrack_output_layout = QFormLayout(self.opentrack_output_group)
        self.opentrack_output_widgets = {'yaw': QLabel("..."), 'pitch': QLabel("..."), 'roll': QLabel("...")}
        opentrack_output_layout.addRow("<b>Yaw:</b>", self.opentrack_output_widgets['yaw'])
        opentrack_output_layout.addRow("<b>Pitch:</b>", self.opentrack_output_widgets['pitch'])
        opentrack_output_layout.addRow("<b>Roll:</b>", self.opentrack_output_widgets['roll'])
        self.controls_layout.addWidget(self.opentrack_output_group)
        self.mapping_group = QGroupBox("OpenTrack Output Mapping")
        mapping_layout = QGridLayout(self.mapping_group)
        self.mapping_widgets = {}
        options = ["yaw", "pitch", "roll", "disabled"]
        for i, axis in enumerate(["yaw", "pitch", "roll"]):
            mapping_layout.addWidget(QLabel(f"<b>Output {axis.capitalize()}:</b>"), i, 0)
            combo = QComboBox()
            combo.addItems(options)
            check = QCheckBox("Invert")
            combo.currentTextChanged.connect(self.mapping_changed)
            check.stateChanged.connect(self.mapping_changed)
            mapping_layout.addWidget(combo, i, 1)
            mapping_layout.addWidget(check, i, 2)
            self.mapping_widgets[axis] = {'combo': combo, 'check': check}
        self.mapping_widgets['yaw']['combo'].setCurrentText('yaw')
        self.mapping_widgets['pitch']['combo'].setCurrentText('pitch')
        self.mapping_widgets['roll']['combo'].setCurrentText('roll')
        self.controls_layout.addWidget(self.mapping_group)
        connection_group = QGroupBox("Connection")
        connection_layout = QFormLayout(connection_group)
        self.port_input = QLineEdit(str(DEFAULT_OPENTRACK_PORT))
        self.port_input.textChanged.connect(self.port_changed)
        connection_layout.addRow("<b>OpenTrack Port:</b>", self.port_input)
        self.reset_button = QPushButton("Reset Tracking (Center)")
        self.reset_button.clicked.connect(self.on_reset_clicked)
        connection_layout.addRow(self.reset_button)
        self.forward_button = QPushButton("Start Forwarding")
        self.forward_button.setCheckable(True)
        self.forward_button.clicked.connect(self.toggle_forwarding)
        self.forward_button.setStyleSheet("background-color: #3c783c;")
        connection_layout.addRow(self.forward_button)
        self.controls_layout.addWidget(connection_group)
        self.controls_layout.addStretch(1)

    def reset_ui_to_waiting(self):
        self.tracker_status_group.hide()
        self.raw_data_group.hide()
        self.mapping_group.hide()
        self.opentrack_output_group.hide()
        self.displayed_tracker_addr = None
        self.last_ui_angles = {'yaw': None, 'pitch': None, 'roll': None}
        self.status_label.show()

    def update_ui(self):
        self.lock.lock()
        trackers_copy = dict(self.trackers)
        self.lock.unlock()
        if self.displayed_tracker_addr and self.displayed_tracker_addr not in trackers_copy:
            self.reset_ui_to_waiting()
            return
        if trackers_copy and not self.displayed_tracker_addr:
            self.displayed_tracker_addr = list(trackers_copy.keys())[0]
            ip, port = self.displayed_tracker_addr
            self.status_label.hide()
            self.info_widgets['name'].setText("Tracker 1")
            self.info_widgets['ip'].setText(f"{ip}:{port}")
            self.tracker_status_group.show()
            self.raw_data_group.show()
            self.mapping_group.show()
            self.opentrack_output_group.show()
        if self.displayed_tracker_addr in trackers_copy:
            data = trackers_copy[self.displayed_tracker_addr]
            self.info_widgets['battery'].setText(data.get("battery", "..."))
            if 'output_angles' in data and 'raw_angles' in data:
                output_yaw, output_pitch, output_roll = data['output_angles']
                last = self.last_ui_angles
                if (last['yaw'] is None or
                    abs(output_yaw - last['yaw']) > DEGREE_CHANGE_THRESHOLD or
                    abs(output_pitch - last['pitch']) > DEGREE_CHANGE_THRESHOLD or
                    abs(output_roll - last['roll']) > DEGREE_CHANGE_THRESHOLD):

                    raw_yaw, raw_pitch, raw_roll = data['raw_angles']
                    self.raw_data_widgets['yaw'].setText(f"{raw_yaw:.1f}°")
                    self.raw_data_widgets['pitch'].setText(f"{raw_pitch:.1f}°")
                    self.raw_data_widgets['roll'].setText(f"{raw_roll:.1f}°")

                    self.opentrack_output_widgets['yaw'].setText(f"{output_yaw:.1f}°")
                    self.opentrack_output_widgets['pitch'].setText(f"{output_pitch:.1f}°")
                    self.opentrack_output_widgets['roll'].setText(f"{output_roll:.1f}°")

                    self.opengl_widget.update_rotation(output_yaw, output_pitch, output_roll)
                    self.last_ui_angles = {'yaw': output_yaw, 'pitch': output_pitch, 'roll': output_roll}

    def mapping_changed(self):
        for out_axis, widgets in self.mapping_widgets.items():
            source = widgets['combo'].currentText()
            invert = widgets['check'].isChecked()
            self.worker.set_mapping(out_axis, source, invert)
            widgets['check'].setEnabled(source != 'disabled')
        self.last_ui_angles = {'yaw': None, 'pitch': None, 'roll': None}

    def toggle_forwarding(self):
        is_checked = self.forward_button.isChecked()
        self.worker.set_forwarding(is_checked)
        if is_checked:
            self.forward_button.setText("Stop Forwarding")
            self.forward_button.setStyleSheet("background-color: #8c3c3c;")
        else:
            self.forward_button.setText("Start Forwarding")
            self.forward_button.setStyleSheet("background-color: #3c783c;")

    def on_reset_clicked(self):
        self.worker.zero_tracker()

    def port_changed(self, text):
        self.worker.set_opentrack_port(text)

    def closeEvent(self, event):
        print("Closing bridge...")
        self.timer.stop()
        self.worker.stop()
        self.thread.quit()
        self.thread.wait()
        event.accept()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    timer = QTimer()
    timer.start(500)
    timer.timeout.connect(lambda: None) 
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())