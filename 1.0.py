from flask import Flask, request, render_template_string, jsonify, session, send_file
from datetime import datetime
import threading
import time
import json
import io
import csv
from collections import defaultdict
from colorama import init, Fore, Style
import secrets

# 初始化颜色输出
init(autoreset=True)

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)

# 全局变量存储统计数据
class Statistics:
    def __init__(self):
        self.active_connections = 0
        self.total_requests = 0
        self.total_data_transferred = 0  # 字节
        self.connection_history = []
        self.request_history = []
        self.data_history = []
        self.user_data = []  # 存储用户信息
        self.lock = threading.Lock()
        self.connection_timestamps = defaultdict(list)
        
    def add_connection(self, ip, user_agent, location=None):
        with self.lock:
            self.active_connections += 1
            self.total_requests += 1
            
            # 记录用户信息
            user_info = {
                'ip': ip,
                'user_agent': user_agent,
                'location': location or '未知',
                'timestamp': datetime.now(),
                'requests': 1
            }
            
            # 检查是否已存在该IP
            existing = next((u for u in self.user_data if u['ip'] == ip), None)
            if existing:
                existing['requests'] += 1
                if location and location != '未知':
                    existing['location'] = location
            else:
                self.user_data.append(user_info)
            
            # 记录历史数据
            now = datetime.now()
            self.connection_history.append({
                'time': now,
                'count': self.active_connections
            })
            self.request_history.append({
                'time': now,
                'count': self.total_requests
            })
            self.data_history.append({
                'time': now,
                'bytes': self.total_data_transferred
            })
            
            # 清理旧数据（保留最近1000条）
            if len(self.connection_history) > 1000:
                self.connection_history = self.connection_history[-1000:]
                self.request_history = self.request_history[-1000:]
                self.data_history = self.data_history[-1000:]
            
            return self.log_message(ip, user_agent, location, '连接请求')
    
    def remove_connection(self, ip):
        with self.lock:
            if self.active_connections > 0:
                self.active_connections -= 1
            self.connection_history.append({
                'time': datetime.now(),
                'count': self.active_connections
            })
    
    def add_data_transfer(self, ip, bytes_transferred=1024 * 1024):  # 默认1MB
        with self.lock:
            self.total_data_transferred += bytes_transferred
            self.data_history.append({
                'time': datetime.now(),
                'bytes': self.total_data_transferred
            })
            return self.log_message(ip, None, None, '数据传输', bytes_transferred)
    
    def log_message(self, ip, user_agent, location, msg_type, data_size=None):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        if msg_type == '连接请求':
            if location:
                message = f"{timestamp} {Fore.GREEN}[{msg_type}]{Style.RESET_ALL} {ip} 连接，使用的UA是{user_agent}, {location}"
            else:
                message = f"{timestamp} {Fore.GREEN}[{msg_type}]{Style.RESET_ALL} {ip} 连接，使用的UA是{user_agent}, 未授权位置信息"
        elif msg_type == '数据传输':
            message = f"{timestamp} {Fore.BLUE}[{msg_type}]{Style.RESET_ALL} {ip} 按下按钮，发送了{data_size/(1024 * 1024):.1f}M的数据"
        elif msg_type == '连接失败':
            message = f"{timestamp} {Fore.RED}[{msg_type}]{Style.RESET_ALL} {ip} 连接失败"
        
        print(message)
        return message

stats = Statistics()

# HTML模板
MAIN_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>系统监控页面</title>
    <meta charset="utf-8">
    <style>
        body {
            font-family: Arial, sans-serif;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            margin: 0;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        }
        .container {
            background: white;
            padding: 40px;
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            text-align: center;
            max-width: 800px;
            width: 90%;
        }
        .info-box {
            background: #f8f9fa;
            padding: 20px;
            border-radius: 10px;
            margin: 20px 0;
            border-left: 5px solid #667eea;
        }
        .button {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            padding: 15px 30px;
            font-size: 16px;
            border-radius: 50px;
            cursor: pointer;
            margin: 10px;
            transition: transform 0.3s, box-shadow 0.3s;
        }
        .button:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 20px rgba(0,0,0,0.2);
        }
        .location-btn {
            background: #4CAF50;
        }
        .data-btn {
            background: #FF5722;
        }
        .status {
            font-size: 14px;
            color: #666;
            margin-top: 20px;
        }
        .location-status {
            padding: 10px;
            background: #e8f5e9;
            border-radius: 5px;
            margin: 10px 0;
        }
    </style>
    <script>
        function getLocation() {
            if (navigator.geolocation) {
                navigator.geolocation.getCurrentPosition(
                    function(position) {
                        document.getElementById('location').innerHTML = 
                            '纬度: ' + position.coords.latitude + 
                            ' 经度: ' + position.coords.longitude;
                        document.getElementById('location-status').innerHTML = '位置已获取';
                        document.getElementById('retry-btn').style.display = 'none';
                        
                        // 发送位置信息到服务器
                        fetch('/update_location', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json',
                            },
                            body: JSON.stringify({
                                latitude: position.coords.latitude,
                                longitude: position.coords.longitude
                            })
                        });
                    },
                    function(error) {
                        document.getElementById('location-status').innerHTML = '位置获取失败';
                        document.getElementById('retry-btn').style.display = 'block';
                    }
                );
            } else {
                document.getElementById('location-status').innerHTML = '浏览器不支持地理位置';
            }
        }
        
        function sendData() {
            fetch('/send_data', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({action: 'send_1mb'})
            }).then(response => response.json())
              .then(data => {
                  document.getElementById('status').innerHTML = data.message;
                  document.getElementById('status').style.color = '#4CAF50';
              })
              .catch(error => {
                  document.getElementById('status').innerHTML = '发送失败';
                  document.getElementById('status').style.color = '#F44336';
              });
        }
        
        // 页面加载时获取位置
        window.onload = getLocation;
    </script>
</head>
<body>
    <div class="container">
        <h1>欢迎访问系统监控</h1>
        <div class="info-box">
            <p><strong>正在访问网站</strong></p>
            <p>您的IP: {{ ip }}</p>
            <p>您的UA: {{ user_agent }}</p>
            <div id="location" class="location-status">
                当前时间位置: {{ current_time }} {{ location }}
            </div>
        </div>
        
        <div id="location-status" class="status">正在获取位置信息...</div>
        
        <button class="button location-btn" onclick="getLocation()">获取位置</button>
        <button id="retry-btn" class="button" onclick="getLocation()" style="display:none;">重新获取</button>
        
        <button class="button data-btn" onclick="sendData()">发送1MB数据</button>
        
        <div id="status" class="status"></div>
    </div>
</body>
</html>
'''

ADMIN_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>管理面板</title>
    <meta charset="utf-8">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body {
            font-family: 'Segoe UI', Arial, sans-serif;
            margin: 0;
            padding: 20px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
        }
        .header {
            background: white;
            padding: 30px;
            border-radius: 15px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.1);
            margin-bottom: 20px;
        }
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
            margin-bottom: 20px;
        }
        .stat-card {
            background: white;
            padding: 25px;
            border-radius: 12px;
            box-shadow: 0 5px 15px rgba(0,0,0,0.08);
        }
        .stat-value {
            font-size: 2.5em;
            font-weight: bold;
            color: #667eea;
            margin: 10px 0;
        }
        .stat-label {
            color: #666;
            font-size: 0.9em;
        }
        .charts-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
            gap: 20px;
            margin-bottom: 20px;
        }
        .chart-container {
            background: white;
            padding: 20px;
            border-radius: 12px;
            box-shadow: 0 5px 15px rgba(0,0,0,0.08);
        }
        canvas {
            width: 100% !important;
            height: 300px !important;
        }
        .users-table {
            background: white;
            border-radius: 12px;
            padding: 20px;
            box-shadow: 0 5px 15px rgba(0,0,0,0.08);
            overflow-x: auto;
        }
        table {
            width: 100%;
            border-collapse: collapse;
        }
        th, td {
            padding: 12px 15px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }
        th {
            background: #f8f9fa;
            font-weight: 600;
        }
        tr:hover {
            background: #f5f5f5;
        }
        .export-btn {
            background: linear-gradient(135deg, #4CAF50 0%, #2E7D32 100%);
            color: white;
            border: none;
            padding: 12px 25px;
            border-radius: 25px;
            cursor: pointer;
            font-size: 16px;
            margin-top: 20px;
            transition: transform 0.3s;
        }
        .export-btn:hover {
            transform: translateY(-2px);
        }
        .logout-btn {
            background: #f44336;
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 20px;
            cursor: pointer;
            float: right;
        }
    </style>
    <script>
        let charts = {};
        
        function formatBytes(bytes, decimals = 2) {
            if (bytes === 0) return '0 Bytes';
            const k = 1024;
            const dm = decimals < 0 ? 0 : decimals;
            const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
            const i = Math.floor(Math.log(bytes) / Math.log(k));
            return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
        }
        
        function updateData() {
            fetch('/admin/api/data')
                .then(response => response.json())
                .then(data => {
                    // 更新统计数据
                    document.getElementById('active-connections').textContent = data.active_connections;
                    document.getElementById('total-requests').textContent = data.total_requests;
                    document.getElementById('data-transferred').textContent = formatBytes(data.total_data_transferred);
                    
                    // 更新图表
                    updateChart('connections-chart', '活跃连接数', data.connection_history);
                    updateChart('requests-chart', '累计请求数', data.request_history);
                    updateChart('data-chart', '数据传输量', data.data_history);
                    
                    // 更新用户表格
                    updateUsersTable(data.user_data);
                });
        }
        
        function updateChart(canvasId, label, data) {
            if (!charts[canvasId]) {
                const ctx = document.getElementById(canvasId).getContext('2d');
                charts[canvasId] = new Chart(ctx, {
                    type: 'line',
                    data: {
                        labels: [],
                        datasets: [{
                            label: label,
                            data: [],
                            borderColor: 'rgb(75, 192, 192)',
                            backgroundColor: 'rgba(75, 192, 192, 0.1)',
                            fill: true,
                            tension: 0.4
                        }]
                    },
                    options: {
                        responsive: true,
                        scales: {
                            x: {
                                display: true,
                                title: {
                                    display: true,
                                    text: '时间'
                                }
                            },
                            y: {
                                display: true,
                                title: {
                                    display: true,
                                    text: label
                                }
                            }
                        }
                    }
                });
            }
            
            const chart = charts[canvasId];
            const labels = data.map(item => new Date(item.time).toLocaleTimeString());
            const values = data.map(item => item.count || item.bytes);
            
            chart.data.labels = labels;
            chart.data.datasets[0].data = values;
            chart.update();
        }
        
        function updateUsersTable(users) {
            const tbody = document.querySelector('#users-table tbody');
            tbody.innerHTML = '';
            
            users.forEach(user => {
                const row = tbody.insertRow();
                row.insertCell().textContent = user.ip;
                row.insertCell().textContent = user.location;
                row.insertCell().textContent = user.user_agent.substring(0, 50) + '...';
                row.insertCell().textContent = new Date(user.timestamp).toLocaleString();
                row.insertCell().textContent = user.requests;
            });
        }
        
        function exportToCSV() {
            window.location.href = '/admin/export';
        }
        
        // 每5秒更新一次数据
        setInterval(updateData, 5000);
        window.onload = updateData;
    </script>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>系统监控面板</h1>
            <button class="logout-btn" onclick="location.href='/admin/logout'">退出登录</button>
        </div>
        
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-label">活跃连接数</div>
                <div class="stat-value" id="active-connections">0</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">累计请求数</div>
                <div class="stat-value" id="total-requests">0</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">消耗数据流量</div>
                <div class="stat-value" id="data-transferred">0 Bytes</div>
            </div>
        </div>
        
        <div class="charts-grid">
            <div class="chart-container">
                <canvas id="connections-chart"></canvas>
            </div>
            <div class="chart-container">
                <canvas id="requests-chart"></canvas>
            </div>
            <div class="chart-container">
                <canvas id="data-chart"></canvas>
            </div>
        </div>
        
        <div class="users-table">
            <h3>用户访问记录</h3>
            <table id="users-table">
                <thead>
                    <tr>
                        <th>用户IP</th>
                        <th>用户位置</th>
                        <th>User Agent</th>
                        <th>最后访问时间</th>
                        <th>请求次数</th>
                    </tr>
                </thead>
                <tbody></tbody>
            </table>
            <button class="export-btn" onclick="exportToCSV()">导出为CSV</button>
        </div>
    </div>
</body>
</html>
'''

LOGIN_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>管理员登录</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            margin: 0;
        }
        .login-container {
            background: white;
            padding: 40px;
            border-radius: 15px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.1);
            width: 300px;
        }
        input {
            width: 100%;
            padding: 10px;
            margin: 10px 0;
            border: 1px solid #ddd;
            border-radius: 5px;
            box-sizing: border-box;
        }
        button {
            width: 100%;
            padding: 10px;
            background: #667eea;
            color: white;
            border: none;
            border-radius: 5px;
            cursor: pointer;
            font-size: 16px;
        }
        button:hover {
            background: #764ba2;
        }
        .error {
            color: red;
            font-size: 14px;
        }
    </style>
</head>
<body>
    <div class="login-container">
        <h2>管理员登录</h2>
        <form method="POST">
            <input type="password" name="password" placeholder="请输入密码" required>
            {% if error %}
            <div class="error">{{ error }}</div>
            {% endif %}
            <button type="submit">登录</button>
        </form>
    </div>
</body>
</html>
'''

@app.route('/')
def index():
    ip = request.remote_addr
    user_agent = request.headers.get('User-Agent')
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # 记录连接
    stats.add_connection(ip, user_agent)
    
    return render_template_string(MAIN_TEMPLATE, 
                                 ip=ip, 
                                 user_agent=user_agent, 
                                 current_time=current_time,
                                 location="正在获取...")

@app.route('/update_location', methods=['POST'])
def update_location():
    data = request.json
    ip = request.remote_addr
    location = f"纬度: {data.get('latitude', '未知')}, 经度: {data.get('longitude', '未知')}"
    
    # 更新用户位置信息
    with stats.lock:
        for user in stats.user_data:
            if user['ip'] == ip:
                user['location'] = location
                break
    
    return jsonify({'status': 'success'})

@app.route('/send_data', methods=['POST'])
def send_data():
    ip = request.remote_addr
    stats.add_data_transfer(ip, 1024 * 1024)  # 1MB
    return jsonify({'status': 'success', 'message': '已发送1MB数据'})

@app.route('/admin', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        password = request.form.get('password')
        if password == '123456':
            session['admin'] = True
            return admin_panel()
        return render_template_string(LOGIN_TEMPLATE, error="密码错误")
    
    if session.get('admin'):
        return admin_panel()
    
    return render_template_string(LOGIN_TEMPLATE)

@app.route('/admin/panel')
def admin_panel():
    if not session.get('admin'):
        return admin_login()
    return render_template_string(ADMIN_TEMPLATE)

@app.route('/admin/api/data')
def admin_data():
    if not session.get('admin'):
        return jsonify({'error': '未授权'}), 401
    
    with stats.lock:
        # 准备最近30个数据点用于图表
        connection_data = stats.connection_history[-30:] if stats.connection_history else []
        request_data = stats.request_history[-30:] if stats.request_history else []
        data_history = stats.data_history[-30:] if stats.data_history else []
        
        return jsonify({
            'active_connections': stats.active_connections,
            'total_requests': stats.total_requests,
            'total_data_transferred': stats.total_data_transferred,
            'connection_history': [{'time': item['time'].isoformat(), 'count': item['count']} 
                                 for item in connection_data],
            'request_history': [{'time': item['time'].isoformat(), 'count': item['count']} 
                              for item in request_data],
            'data_history': [{'time': item['time'].isoformat(), 'bytes': item['bytes']} 
                           for item in data_history],
            'user_data': [{
                'ip': user['ip'],
                'location': user['location'],
                'user_agent': user['user_agent'],
                'timestamp': user['timestamp'].isoformat(),
                'requests': user['requests']
            } for user in stats.user_data[-50:]]  # 只返回最近50个用户
        })

@app.route('/admin/export')
def export_data():
    if not session.get('admin'):
        return jsonify({'error': '未授权'}), 401
    
    # 创建CSV文件
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['IP地址', '位置', 'User Agent', '最后访问时间', '请求次数'])
    
    with stats.lock:
        for user in stats.user_data:
            writer.writerow([
                user['ip'],
                user['location'],
                user['user_agent'],
                user['timestamp'].strftime("%Y-%m-%d %H:%M:%S"),
                user['requests']
            ])
    
    output.seek(0)
    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8')),
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'user_data_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
    )

@app.route('/admin/logout')
def logout():
    session.pop('admin', None)
    return '<script>alert("已退出登录"); window.location.href="/admin";</script>'

@app.before_request
def before_request():
    # 记录每个请求的时间戳
    if request.remote_addr:
        stats.connection_timestamps[request.remote_addr].append(time.time())

@app.after_request
def after_request(response):
    # 清理超过30秒不活跃的连接
    current_time = time.time()
    with stats.lock:
        for ip in list(stats.connection_timestamps.keys()):
            # 保留最近30秒内的连接
            stats.connection_timestamps[ip] = [
                ts for ts in stats.connection_timestamps[ip] 
                if current_time - ts < 30
            ]
            # 如果最近30秒内没有连接，则移除
            if not stats.connection_timestamps[ip]:
                del stats.connection_timestamps[ip]
        
        # 更新活跃连接数
        stats.active_connections = len(stats.connection_timestamps)
    
    return response

if __name__ == '__main__':
    print(Fore.CYAN + "="*60)
    print(Fore.YELLOW + "系统启动中...")
    print(Fore.GREEN + f"服务器将在 127.0.0.1:2250 上运行")
    print(Fore.CYAN + f"访问地址: http://127.0.0.1:2250")
    print(Fore.CYAN + f"管理面板: http://127.0.0.1:2250/admin")
    print(Fore.YELLOW + "管理员密码: 123456")
    print(Fore.CYAN + "="*60)
    print(Style.RESET_ALL)
    
    app.run(host='127.0.0.1', port=2250, debug=False)
