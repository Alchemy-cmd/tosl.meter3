import time
import json
from pymodbus.client import ModbusTcpClient
from flask import Flask, render_template, jsonify
from flask import request, Response

# Meter configuration
METER_IP = "10.10.100.254"
METER_PORT = 8899
SLAVE_ID = 5

# Registers
REGISTERS = {
    "inlet_temp": 4140,
    "outlet_temp": 4141,
    "flow_rate": 4114,    
    "instant_heat": 4134,
    "total_heat_int": 4136, 
    "total_heat_dec": 4138,
}

app = Flask(__name__)
USERNAME = "ToslAdmin"
PASSWORD = "ToslPass"

def check_auth(username, password):
    return username == USERNAME and password == PASSWORD

def authenticate():
    return Response(
        'Access Denied.\n'
        'Please provide valid credentials.', 
        401, 
        {'WWW-Authenticate': 'Basic realm="Login Required"'}
    )

@app.before_request
def require_auth():
    auth = request.authorization
    if not auth or not check_auth(auth.username, auth.password):
        return authenticate()
        
# Initial readings
latest_readings = {
    "inlet_temp": 0.0,
    "outlet_temp": 0.0,
    "temperature_diff": 0.0,
    "flow_rate": 0.0,
    "instant_energy": 0.0,
    "total_energy": 0.0,
    "timestamp": ""
}

# Read btu data
def read_meter_data():
    try:
        client = ModbusTcpClient(host=METER_IP, port=METER_PORT)
        client.connect()
        
        # Inlet Temperature
        inlet_temp_response = client.read_holding_registers(address=REGISTERS["inlet_temp"], count=1, slave=SLAVE_ID)
        if not inlet_temp_response.isError():
            inlet_temp_raw = inlet_temp_response.registers[0]
            inlet_temp = inlet_temp_raw / 10.0
        else:
            inlet_temp = None
            print("Failed to read inlet temperature")
            
        # Outlet Temperature
        outlet_temp_response = client.read_holding_registers(address=REGISTERS["outlet_temp"], count=1, slave=SLAVE_ID)
        if not outlet_temp_response.isError():
            outlet_temp_raw = outlet_temp_response.registers[0]
            outlet_temp = outlet_temp_raw / 10.0
        else:
            outlet_temp = None
            print("Failed to read outlet temperature")
            
        # Flow Rate
        flow_response = client.read_holding_registers(address=REGISTERS["flow_rate"], count=2, slave=SLAVE_ID)
        if not flow_response.isError():
            flow_registers = flow_response.registers
            flow_rate = decode_ieee754_inverse(flow_registers)
        else:
            flow_rate = None
            print("Failed to read flow rate")
            
        # Instantaneous Heat Energy
        energy_response = client.read_holding_registers(address=REGISTERS["instant_heat"], count=2, slave=SLAVE_ID)
        if not energy_response.isError():
            energy_registers = energy_response.registers
            instant_energy = decode_ieee754_inverse(energy_registers)
        else:
            instant_energy = None
            print("Failed to read instantaneous heat")
            
        # Total Heat Integer Part
        total_heat_int_response = client.read_holding_registers(address=REGISTERS["total_heat_int"], count=2, slave=SLAVE_ID)
        if not total_heat_int_response.isError():
            total_heat_int_registers = total_heat_int_response.registers
            total_heat_int = (total_heat_int_registers[1] << 16) | total_heat_int_registers[0]
        else:
            total_heat_int = 0
            print("Failed to read total heat integer part")
            
        # Total Heat Decimal Part
        total_heat_dec_response = client.read_holding_registers(address=REGISTERS["total_heat_dec"], count=2, slave=SLAVE_ID)
        if not total_heat_dec_response.isError():
            total_heat_dec_registers = total_heat_dec_response.registers
            total_heat_dec = decode_ieee754_inverse(total_heat_dec_registers)
        else:
            total_heat_dec = 0
            print("Failed to read total heat decimal part")
            
        # Total Energy
        total_energy = total_heat_int + total_heat_dec if total_heat_int is not None and total_heat_dec is not None else None
            
        client.close()
        
        if all(x is not None for x in [inlet_temp, outlet_temp, flow_rate, instant_energy, total_energy]):
            latest_readings["inlet_temp"] = inlet_temp
            latest_readings["outlet_temp"] = outlet_temp
            latest_readings["temperature_diff"] = inlet_temp - outlet_temp
            latest_readings["flow_rate"] = flow_rate
            latest_readings["instant_energy"] = instant_energy
            latest_readings["total_energy"] = total_energy
            latest_readings["timestamp"] = time.strftime("%Y-%m-%d %H:%M:%S")
            return True
        else:
            print("Error reading one or more values from meter")
            return False
            
    except Exception as e:
        print(f"Error connecting to meter: {e}")
        return False

def decode_ieee754(registers):
    import struct
    if len(registers) != 2:
        return None
    
    combined = (registers[0] << 16) | registers[1]
    
    packed = struct.pack('>I', combined)
    unpacked = struct.unpack('>f', packed)[0]
    return unpacked

def decode_ieee754_inverse(registers):
    import struct
    if len(registers) != 2:
        return None
    
    combined = (registers[1] << 16) | registers[0]
    
    packed = struct.pack('<I', combined)
    unpacked = struct.unpack('<f', packed)[0]
    return unpacked

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/data')
def get_data():
    if not read_meter_data():
        return jsonify({"error": "Failed to fetch meter data"})
    return jsonify(latest_readings)

def update_readings_loop():
    import threading
    
    def update_loop():
        while True:
            read_meter_data()
            time.sleep(10)
            
    update_thread = threading.Thread(target=update_loop)
    update_thread.daemon = True
    update_thread.start()

if __name__ == "__main__":
    import os
    if not os.path.exists("templates"):
        os.makedirs("templates")
        
    with open("templates/index.html", "w", encoding="utf-8") as f:
        f.write("""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>BTU METER Monitor</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f5;
        }
        .dashboard {
            background-color: white;
            border-radius: 10px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            padding: 20px;
            margin-top: 20px;
        }
        .section {
            border-bottom: 1px solid #eee;
            padding-bottom: 15px;
            margin-bottom: 15px;
        }
        .section-title {
            font-size: 18px;
            font-weight: bold;
            color: #444;
            margin-bottom: 15px;
        }
        .meter-reading {
            display: flex;
            margin-bottom: 15px;
            align-items: center;
        }
        .reading-label {
            font-weight: bold;
            width: 180px;
        }
        .reading-value {
            font-size: 20px;
            margin-left: 10px;
            min-width: 80px;
            text-align: right;
        }
        .reading-unit {
            color: #666;
            margin-left: 10px;
            width: 60px;
        }
        .timestamp {
            color: #666;
            font-size: 12px;
            text-align: right;
            margin-top: 20px;
        }
        h1 {
            color: #333;
            text-align: center;
        }
    </style>
</head>
<body>
    <h1>Building 3 Heat Meter Dashboard</h1>
    
    <div class="dashboard">
        <div class="section">
            <div class="section-title">Temperature Readings</div>
            <div class="meter-reading">
                <div class="reading-label">Inlet Temperature:</div>
                <div class="reading-value" id="inlet-temp">--</div>
                <div class="reading-unit">°C</div>
            </div>
            
            <div class="meter-reading">
                <div class="reading-label">Outlet Temperature:</div>
                <div class="reading-value" id="outlet-temp">--</div>
                <div class="reading-unit">°C</div>
            </div>
            
            <div class="meter-reading">
                <div class="reading-label">Temperature Difference:</div>
                <div class="reading-value" id="temp-diff">--</div>
                <div class="reading-unit">°C</div>
            </div>
        </div>
        
        <div class="section">
            <div class="section-title">Flow Readings</div>
            <div class="meter-reading">
                <div class="reading-label">Flow Rate:</div>
                <div class="reading-value" id="flow-rate">--</div>
                <div class="reading-unit">m³/h</div>
            </div>
        </div>
        
        <div class="section">
            <div class="section-title">Energy Readings</div>
            <div class="meter-reading">
                <div class="reading-label">Instantaneous Energy:</div>
                <div class="reading-value" id="instant-energy">--</div>
                <div class="reading-unit">MJ</div>
            </div>
            
            <div class="meter-reading">
                <div class="reading-label">Total Accumulated Energy:</div>
                <div class="reading-value" id="total-energy">--</div>
                <div class="reading-unit">MJ</div>
            </div>
        </div>
        
        <div class="timestamp" id="timestamp">Last updated: --</div>
    </div>
    
    <script>
        // Function to update the dashboard with latest readings
        function updateReadings() {
            fetch('/data')
                .then(response => response.json())
                .then(data => {
                    document.getElementById('inlet-temp').textContent = data.inlet_temp.toFixed(1);
                    document.getElementById('outlet-temp').textContent = data.outlet_temp.toFixed(1);
                    document.getElementById('temp-diff').textContent = data.temperature_diff.toFixed(1);
                    document.getElementById('flow-rate').textContent = data.flow_rate.toFixed(2);
                    document.getElementById('instant-energy').textContent = data.instant_energy.toFixed(1);
                    document.getElementById('total-energy').textContent = data.total_energy.toFixed(0);
                    document.getElementById('timestamp').textContent = 'Last updated: ' + data.timestamp;
                })
                .catch(error => console.error('Error fetching data:', error));
        }
        
        updateReadings();
        setInterval(updateReadings, 1000);
    </script>
</body>
</html>""")
    
    update_readings_loop()
    app.run(host='0.0.0.0', port=5000)
