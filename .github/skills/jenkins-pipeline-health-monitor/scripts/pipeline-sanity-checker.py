#!/usr/bin/env python3
"""Jenkins Pipeline Health Monitor - Checks Jenkins pipeline every 5 minutes"""

import requests
import time
import sys
import os
import urllib3
import threading
from datetime import datetime, timedelta
from prometheus_client import Gauge, Counter, start_http_server
import pickle

# Find and import DB_Tools
current_dir = os.path.dirname(os.path.abspath(__file__))
print(current_dir)
for path in [
    current_dir,
    os.path.join(current_dir, '..', '..', 'CI_Tools', 'NEW_CI_XML_PARSER'),
    os.path.join(os.path.dirname(os.path.dirname(current_dir)), 'CI_Tools', 'NEW_CI_XML_PARSER'),
]:
    if os.path.exists(os.path.join(path, 'DB_Tools')):
        sys.path.insert(0, path)
        break

try:
    from DB_Tools.DB_Writer import DB_Writer
    DB_TOOLS_AVAILABLE = True
except ImportError:
    print("⚠️  DB_Tools not available - database operations will be simulated")
    DB_TOOLS_AVAILABLE = False

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Metrics and configuration
pipeline_success_gauge = Gauge('jenkins_pipeline_success', 'Jenkins pipeline success (1=success, 0=failure)', ['jenkins_url'])
pipeline_check_counter = Counter('jenkins_pipeline_checks_total', 'Total Jenkins pipeline checks', ['jenkins_url'])
pipeline_up_counter = Counter('jenkins_pipeline_up_total', 'Total successful pipeline runs', ['jenkins_url'])
pipeline_down_counter = Counter('jenkins_pipeline_down_total', 'Total failed pipeline runs', ['jenkins_url'])
JENKINS_URL = os.getenv('JENKINS_PIPELINE_URL', "https://cje-il-prod01.devtools.intel.com/epg-sie-ethfwjn/job/Development/job/dev-gbergman/job/sanity_pipeline/")

# Initialize counters with default values
pipeline_up_counter.labels(jenkins_url=JENKINS_URL)._value._value = 0
pipeline_down_counter.labels(jenkins_url=JENKINS_URL)._value._value = 0

class DatabaseHandler:
    def __init__(self, fernet_key=None):
        self.state_file = "jenkins_health_state.pkl"
        self.downtime_state_file = "jenkins_downtime_state.pkl"
        self.last_keepalive = self._load_keepalive()
        self.current_downtime_id = self._load_downtime_state()
        self.fernet_key = fernet_key or os.getenv('DB_FERNET_KEY')
        self.db_writer = self._init_db()
    
    def _init_db(self):
        if DB_TOOLS_AVAILABLE and self.fernet_key:
            try:
                db_writer = DB_Writer(fernet_key=self.fernet_key, db_is_fw_ci_db=False, db_is_devops_infra_monitoring=True, logger=None)
                print("✅ Database writer initialized")
                return db_writer
            except Exception as e:
                print(f"⚠️  DB initialization failed: {e}")
        else:
            print("⚠️  DB_Tools not available - operations simulated")
        return None
    
    def _load_keepalive(self):
        try:
            if os.path.exists(self.state_file):
                with open(self.state_file, 'rb') as f:
                    return pickle.load(f)
        except:
            pass
        return None
    
    def _save_keepalive(self, timestamp):
        try:
            with open(self.state_file, 'wb') as f:
                pickle.dump(timestamp, f)
            self.last_keepalive = timestamp
        except:
            pass
    
    def _load_downtime_state(self):
        """Load current downtime ID if there's an ongoing downtime"""
        try:
            if os.path.exists(self.downtime_state_file):
                with open(self.downtime_state_file, 'rb') as f:
                    return pickle.load(f)
        except:
            pass
        return None
    
    def _save_downtime_state(self, downtime_id):
        """Save current downtime ID"""
        try:
            with open(self.downtime_state_file, 'wb') as f:
                pickle.dump(downtime_id, f)
            self.current_downtime_id = downtime_id
        except:
            pass
    
    def _clear_downtime_state(self):
        """Clear downtime state when uptime is restored"""
        try:
            if os.path.exists(self.downtime_state_file):
                os.remove(self.downtime_state_file)
            self.current_downtime_id = None
        except:
            pass
    
    def _execute_query(self, sql):
        try:
            if self.db_writer:
                self.db_writer.DB_write_connector.execute_write_query(sql_query=sql)
                return True
            else:
                print(f"🔄 [SIMULATED] {sql[:50]}...")
                return True
        except Exception as e:
            print(f"❌ Database error: {e}")
            return False
    
    def record_down(self):
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        pipeline_url = os.getenv('JENKINS_PIPELINE_URL', JENKINS_URL)
        sql = f"INSERT INTO tbl_JenkinsHealth (start_time, status, pipeline_url) VALUES ('{now}', 'down', '{pipeline_url}')"
        if self._execute_query(sql):
            print(f"📊 DOWN recorded")
    
    def record_keepalive(self):
        """Record keepalive status in database - called by background thread"""
        now = datetime.now()
        pipeline_url = os.getenv('JENKINS_PIPELINE_URL', JENKINS_URL)
        sql = f"INSERT INTO tbl_JenkinsHealth (start_time, status, pipeline_url) VALUES ('{now.strftime('%Y-%m-%d %H:%M:%S')}', 'keepalive', '{pipeline_url}')"
        if self._execute_query(sql):
            print(f"📊 Keepalive recorded at {now.strftime('%H:%M:%S')}")
            self._save_keepalive(now)
        return True
    
    def start_downtime(self):
        """Record start of downtime period - only called on first failure"""
        if self.current_downtime_id is not None:
            # Already in downtime, don't create new record
            return
        
        now = datetime.now()
        pipeline_url = os.getenv('JENKINS_PIPELINE_URL', JENKINS_URL)
        
        # Generate unique ID: full millisecond timestamp
        downtime_id = int(now.timestamp() * 1000)  # Full milliseconds since epoch
        
        # Insert new downtime record with our generated ID
        sql = f"INSERT INTO JenkinsDowntime (id, start_time, pipeline_url) VALUES ({downtime_id}, '{now.strftime('%Y-%m-%d %H:%M:%S')}', '{pipeline_url}')"
        if self._execute_query(sql):
            self._save_downtime_state(downtime_id)
            print(f"📊 Downtime started - ID: {downtime_id}")
    
    def end_downtime(self):
        """Record end of downtime period - only called on first success after failure"""
        if self.current_downtime_id is None:
            # Not in downtime, nothing to end
            return
        
        now = datetime.now()
        
        # Update the existing downtime record with end_time
        sql = f"UPDATE JenkinsDowntime SET end_time = '{now.strftime('%Y-%m-%d %H:%M:%S')}' WHERE id = {self.current_downtime_id}"
        if self._execute_query(sql):
            print(f"📊 Downtime ended - ID: {self.current_downtime_id}")
            self._clear_downtime_state()

db_handler = DatabaseHandler()

def keepalive_thread():
    """Background thread that sends keepalive to database every hour"""
    print("🔄 Keepalive thread started - will record every hour")
    
    # Check if we need to record immediate keepalive (no previous state)
    if db_handler.last_keepalive is None:
        print("📊 No previous keepalive found - recording initial keepalive")
        try:
            db_handler.record_keepalive()
        except Exception as e:
            print(f"❌ Initial keepalive failed: {e}")
    
    while True:
        try:
            time.sleep(3600)  # Sleep for 1 hour (3600 seconds)
            db_handler.record_keepalive()
        except Exception as e:
            print(f"❌ Keepalive thread error: {e}")
            time.sleep(60)  # Wait 1 minute before retrying

class JenkinsTrigger:
    def __init__(self, jenkins_url):
        self.username = os.getenv('JENKINS_USERNAME')
        self.api_token = os.getenv('JENKINS_API_TOKEN')
        self.proxies = {'http': os.getenv('HTTP_PROXY'), 'https': os.getenv('HTTP_PROXY')} if os.getenv('HTTP_PROXY') else None
        self.verify_ssl = False  # Disable for corporate environments
        
        parts = jenkins_url.split('/job/')
        self.base_url = parts[0]
        self.job_path = '/job/'.join(parts[1:])
    
    def trigger(self):
        auth = (self.username, self.api_token) if self.username and self.api_token else None
        build_url = f"{self.base_url}/job/{self.job_path}/build"
        
        # Get CSRF crumb
        headers = {'Content-Type': 'application/x-www-form-urlencoded'}
        try:
            crumb_url = f"{self.base_url}/crumbIssuer/api/json"
            crumb_response = requests.get(crumb_url, auth=auth, proxies=self.proxies, verify=False, timeout=10)
            if crumb_response.status_code == 200:
                crumb = crumb_response.json()
                headers[crumb['crumbRequestField']] = crumb['crumb']
        except:
            pass
        
        print("Triggering pipeline...")
        try:
            response = requests.post(build_url, auth=auth, headers=headers, proxies=self.proxies, verify=False, timeout=30)
            if response.status_code in [200, 201]:
                location = response.headers.get('Location', '')
                queue_id = location.split('/')[-2] if location.endswith('/') else location.split('/')[-1]
                print(f"Queued: {queue_id}")
                return True, queue_id
            else:
                return False, f"HTTP {response.status_code}"
        except Exception as e:
            return False, f"Network error: {str(e)}"
    
    def wait_for_result(self, queue_id, timeout=20):
        if not queue_id:
            return False, "No queue ID"
        
        auth = (self.username, self.api_token) if self.username and self.api_token else None
        print(f"Waiting {timeout}s...")
        time.sleep(timeout)
        
        try:
            # Get build number from queue
            queue_url = f"{self.base_url}/queue/item/{queue_id}/api/json"
            response = requests.get(queue_url, auth=auth, proxies=self.proxies, verify=False, timeout=10)
            
            if response.status_code == 200:
                queue_data = response.json()
                if 'executable' in queue_data:
                    build_number = queue_data['executable']['number']
                    
                    # Check build status
                    build_url = f"{self.base_url}/job/{self.job_path}/{build_number}/api/json"
                    build_response = requests.get(build_url, auth=auth, proxies=self.proxies, verify=False, timeout=10)
                    
                    if build_response.status_code == 200:
                        build_data = build_response.json()
                        if not build_data.get('building', True):
                            result = build_data.get('result')
                            return result == 'SUCCESS', f"Build {build_number}: {result}"
                        else:
                            return False, f"Build {build_number} timeout ({timeout}s)"
            
            return False, f"Timeout after {timeout}s"
        except Exception as e:
            return False, f"Status check error: {str(e)}"


def run_pipeline_check():
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"\n[{timestamp}] Jenkins Pipeline Check")
    print("=" * 50)
    
    trigger = JenkinsTrigger(JENKINS_URL)
    
    try:
        # Trigger pipeline
        success, result = trigger.trigger()
        if not success:
            print(f"❌ Trigger failed: {result}")
            pipeline_success_gauge.labels(jenkins_url=JENKINS_URL).set(0)
            pipeline_check_counter.labels(jenkins_url=JENKINS_URL).inc()
            pipeline_down_counter.labels(jenkins_url=JENKINS_URL).inc()
            db_handler.record_down()
            db_handler.start_downtime()  # Track downtime start
            return False
        
        # Wait for result
        success, message = trigger.wait_for_result(result, timeout=20)
        
        # Update metrics
        pipeline_success_gauge.labels(jenkins_url=JENKINS_URL).set(1 if success else 0)
        pipeline_check_counter.labels(jenkins_url=JENKINS_URL).inc()
        
        if success:
            pipeline_up_counter.labels(jenkins_url=JENKINS_URL).inc()
            print(f"🎉 SUCCESS: {message}")
            print("✅ Metrics updated | ℹ️  UP not recorded in DB")
            db_handler.end_downtime()  # End downtime if we were in one
        else:
            pipeline_down_counter.labels(jenkins_url=JENKINS_URL).inc()
            print(f"❌ FAILED: {message}")
            print("📊 Metrics updated | Recording DOWN in DB")
            db_handler.record_down()
            db_handler.start_downtime()  # Track downtime start
        
        return success
        
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        pipeline_success_gauge.labels(jenkins_url=JENKINS_URL).set(0)
        pipeline_check_counter.labels(jenkins_url=JENKINS_URL).inc()
        pipeline_down_counter.labels(jenkins_url=JENKINS_URL).inc()
        db_handler.record_down()
        db_handler.start_downtime()  # Track downtime start
        return False

def run_monitor():
    print("Jenkins Pipeline Monitor - Every 5 minutes")
    print("=" * 50)
    
    # Start metrics server
    port = int(os.getenv('PROMETHEUS_PORT', '8002'))
    try:
        start_http_server(port)
        print(f"📊 Metrics: http://localhost:{port}/metrics")
    except Exception as e:
        print(f"⚠️  Metrics server failed: {e}")
    
    # Start keepalive background thread
    keepalive_worker = threading.Thread(target=keepalive_thread, daemon=True)
    keepalive_worker.start()
    
    print("Press Ctrl+C to stop")
    
    # Run checks with fixed 5-minute intervals from start time
    while True:
        try:
            start_time = time.time()
            run_pipeline_check()
            
            # Calculate how long to wait for next 5-minute interval
            elapsed = time.time() - start_time
            next_run = 300 - elapsed  # 300 seconds = 5 minutes
            
            if next_run > 0:
                print(f"\n⏰ Waiting {next_run:.1f}s until next check...")
                time.sleep(next_run)
            else:
                print(f"\n⚠️  Check took {elapsed:.1f}s (longer than 5min interval)")
                
        except KeyboardInterrupt:
            print("\n👋 Stopped")
            break
        except Exception as e:
            print(f"❌ Error: {e}")
            time.sleep(30)

def main():
    if len(sys.argv) > 1 and sys.argv[1].lower() in ['--monitor', '-m']:
        run_monitor()
    else:
        print("Jenkins Pipeline Health Monitor")
        print("Usage:")
        print("  python pipeline-sanity-checker.py           # Run once")
        print("  python pipeline-sanity-checker.py --monitor # Run every 5 minutes")
        print()
        success = run_pipeline_check()
        return 0 if success else 1

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nInterrupted")
        sys.exit(130)