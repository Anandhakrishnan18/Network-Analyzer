# NetPulse — Viva Voce & Technical Demonstration Guide

This guide is designed for B.Tech Computer Science / Information Technology students presenting the **Internet Quality Analyzer & Connection Troubleshooter** to college project review committees, external viva examiners, and technical interviewers.

---

## 🎯 1. The 60-Second Elevator Pitch

> *"Most users complain of 'slow internet' whenever a video call freezes or a web page lags, relying on conventional speed tests that only report bandwidth in Mbps. But bandwidth is like the width of a highway; latency, jitter, packet loss, DNS lookup time, and local Wi-Fi congestion are the traffic signals, potholes, and detours.*
> 
> *NetPulse is a multi-layer diagnostic system. It automatically discovers the local default router to establish a hop-1 baseline, measures L3 ICMP latency and consecutive-packet jitter, L4 TCP 3-way handshake times, and L7 DNS resolution directly against Anycast resolvers to bypass OS caching. It feeds this telemetry into a deterministic, rule-based troubleshooting engine that produces quantitative evidence, root-cause isolation (differentiating local Wi-Fi from ISP WAN problems), actionable recommendations, and differential session comparison with RFC 4180 CSV and JSON data export."*

---

## 🎬 2. 5-Minute Live Demonstration Walkthrough Script

Follow these steps in sequence during your demonstration:

### Step 1: Gateway Auto-Discovery & Health Check
1. Start the server: `python app.py`.
2. Open `http://127.0.0.1:5000`.
3. **What to point out:**
   - In the top navigation bar, point to the green indicator chip: **"Detecting network... -> Connected (192.168.1.50) | Gateway: 192.168.1.1"**.
   - **Viva Explanation:** *"The application automatically parses the operating system's routing table (`route print 0.0.0.0` on Windows) on startup to isolate the first hop — the local gateway router. This is the cornerstone of our LAN vs. WAN differential diagnosis."*

### Step 2: Trigger Live Diagnostics
1. Click the blue **"Run Diagnostics"** button.
2. The button spinner activates, and live probes begin.
3. Once completed (~5–8 seconds), show:
   - **Overall Connection Status Card** (e.g., *Healthy* or *Warning*).
   - **Average ICMP Latency** (L3 Round Trip Time).
   - **RFC Jitter** (Mean consecutive packet delay variance).
   - **Packet Loss %** (Unanswered probe percentage).
   - **DNS Resolution** (UDP/53 lookup time).
   - **TCP 3-Way Handshake** (L4 connection establishment).

### Step 3: Show Explainable Troubleshooting Findings
1. Scroll to the **"Explainable Troubleshooting"** panel on the left.
2. Click on any active finding.
3. **What to point out:**
   - Notice that every finding contains:
     - **Symptom:** Plain-English summary.
     - **Quantitative Evidence:** Actual measured numbers vs. configured thresholds (e.g., `Gateway Latency 20.2ms > Warning 15.0ms`).
     - **Possible Causes:** Technical root causes (RF interference, bufferbloat).
     - **Recommendations:** Concrete remediation steps (switch to 5 GHz Wi-Fi, enable SQM).
     - **Confidence Level & Limitations:** Scientific caveats acknowledging router firewall behaviors.
   - **Viva Explanation:** *"Unlike black-box AI or basic speed tests, our engine is completely explainable and deterministic. It backs every assertion with quantitative telemetry and documents its limitations."*

### Step 4: Visual Telemetry Charts & DNS Benchmarking
1. Scroll to the right column:
   - **Historical Latency & Loss Chart:** Dual-axis timeline showing gateway latency (green), external target latency (blue), and packet loss (red dashed line).
   - **Comparative DNS Resolver Benchmark Chart:** Bar chart comparing System Default vs. Cloudflare (`1.1.1.1`) vs. Google (`8.8.8.8`) vs. Quad9 (`9.9.9.9`).
2. Toggle the timeframe chips (`1h`, `24h`, `7d`) to show dynamic data filtering.

### Step 5: Automated Periodic Monitoring & Threshold Alerts
1. In the top controls card, select `Every 1 min` and click **"Start Monitoring"**.
2. Show the pulsing green indicator dot confirming the background daemon is active.
3. Explain: *"The daemon runs in a synchronized background worker thread with re-entrant lock protection. If metrics exceed threshold limits, it immediately writes an alert record to SQLite and broadcasts it to the dashboard alert banner."*
4. Click **"Stop Monitoring"** to show clean, idempotent thread shutdown.

### Step 6: Head-to-Head Differential Session Comparison
1. In the **"Recent Test Sessions"** table at the bottom:
   - Check the select checkbox on Run #7.
   - Check the select checkbox on Run #1.
2. Notice the button **"Compare Sessions (2)"** appears. Click it.
3. The **"Differential Session Comparison"** modal opens:
   - Point out the **Trend Badge** (`Improved` or `Degraded`).
   - Point out the **Aggregate Deltas**: $\Delta \text{Latency}$, $\Delta \text{Loss}$, $\Delta \text{Jitter}$.
   - Point out the **Target-by-Target Breakdown Table** comparing each destination side-by-side.
4. Click **"Export CSV"** and **"Export JSON"** in the modal header to demonstrate report generation.

---

## 🎓 3. Anticipated Viva Voce Questions & Model Answers

### Category 1: Computer Networks Fundamentals

#### Q1: "Why is a conventional speed test insufficient to troubleshoot video conferencing or online gaming lag?"
> **Model Answer:**
> *"A conventional speed test saturates the network connection to measure maximum download/upload capacity in Mbps. However, video conferencing (Zoom/Teams) and online gaming use lightweight UDP streams requiring minimal bandwidth (~1.5–3 Mbps). They are extremely sensitive to **latency, jitter (packet delay variation), and packet loss**. A user can have a 500 Mbps connection, but if their router suffers from bufferbloat (high jitter) or Wi-Fi packet drops, video calls will freeze. NetPulse isolates latency, jitter, DNS, and TCP handshake times directly rather than just throughput."*

#### Q2: "What is the mathematical formula for Jitter, and why not just use standard deviation?"
> **Model Answer:**
> *"We use the standard RFC formulation for network jitter: the mean absolute difference between consecutive packet arrival times:
> $$\text{Jitter} = \frac{1}{M - 1} \sum_{i=1}^{M - 1} |RTT_{i+1} - RTT_i|$$
> Standard deviation measures dispersion around the overall mean across the entire duration. In networking, gradual diurnal latency changes (e.g., latency rising from 20ms to 40ms over an hour) would inflate standard deviation, even though individual consecutive packets arrive smoothly with zero jitter. Consecutive difference jitter measures true short-term packet delay variation, which is what directly causes packet buffer overruns in real-time media codecs."*

#### Q3: "How does your jitter calculation handle lost or dropped packets?"
> **Model Answer:**
> *"If a packet is lost, it has no valid RTT. Fabricating a zero or substituting the timeout duration would mathematically corrupt the variance calculation. Our algorithm implements strict gap preservation: if packet $i$ or packet $i+1$ is missing (`None`), that gap is skipped from the summation, and $M$ tracks the count of genuinely consecutive received pairs. If fewer than 2 valid pairs remain, jitter is reported as `None` alongside an explicit 100% loss report."*

#### Q4: "How does your system distinguish between a local Wi-Fi issue and an upstream ISP problem?"
> **Model Answer:**
> *"Through **differential analysis relative to the default gateway**. On startup, NetPulse queries the routing table to find the IP of the hop-1 gateway (the local home router). 
> - If latency is high or packet loss occurs on the gateway hop, the problem is 100% local — such as 2.4 GHz co-channel Wi-Fi interference, wall attenuation, or router CPU load.
> - If the gateway hop is pristine (e.g., 1.5ms, 0% loss), but external targets (Cloudflare, Google) show 120ms latency and 15% loss, the local network is exonerated, and the fault is mathematically proven to lie on the upstream ISP backhaul or peering links."*

#### Q5: "Why did you use dnspython instead of Python's built-in `socket.gethostbyname`?"
> **Model Answer:**
> *"`socket.gethostbyname` invokes the operating system's stub resolver (e.g., the Windows DNS Client service). The OS caches DNS responses (`ipconfig /displaydns`). Consequently, the first query might take 40ms, and subsequent calls take 0.1ms from RAM cache, masking external DNS latency.
> By using `dnspython`, our engine creates explicit UDP datagram sockets directly to destination nameservers (`1.1.1.1`, `8.8.8.8`, `9.9.9.9`) on port 53. This bypasses the OS client cache and measures actual network round-trip resolution latency, allowing us to perform true cold and warm benchmarks."*

#### Q6: "Explain the difference between L3 ICMP Ping and L4 TCP 3-Way Handshake Timing."
> **Model Answer:**
> *"ICMP operates at Layer 3 (Network Layer). An ICMP Echo Request is processed directly in the kernel IP stack without creating any socket state.
> TCP operates at Layer 4 (Transport Layer). A TCP connection requires a stateful 3-way handshake: Client sends `SYN`, Server replies `SYN-ACK`, Client returns `ACK`. 
> Under normal conditions, TCP handshake time equals approximately 1 network RTT plus minor OS listen queue scheduling. If ICMP RTT is 20ms but TCP Handshake is 180ms, it indicates the destination server is suffering from TCP listen backlog congestion, socket starvation, or intermediate firewall state inspection delay."*

#### Q7: "What is Bufferbloat, and how does your diagnostic engine detect it?"
> **Model Answer:**
> *"Bufferbloat occurs when network routers and modems contain excessively large, unmanaged packet buffers (FIFO queues). Under heavy traffic (like an upload), packets sit in queue buffers for hundreds of milliseconds instead of being dropped to signal TCP congestion control.
> NetPulse detects bufferbloat when ping packets exhibit zero or low loss, but consecutive jitter spikes above our warning threshold (>30ms) with large latency fluctuations. The engine triggers `RULE_HIGH_JITTER_BUFFERBLOAT` and recommends Smart Queue Management (SQM like `fq_codel` or `CAKE`)."*

---

### Category 2: Software Architecture & Implementation

#### Q8: "Why did you choose SQLite in WAL mode instead of MySQL or PostgreSQL?"
> **Model Answer:**
> *"For a desktop-deployed diagnostic tool or lightweight edge probe, requiring an external RDBMS daemon like MySQL introduces unnecessary operational overhead and configuration failure points. 
> SQLite is zero-configuration and serverless. By default, SQLite uses rollback journal mode which locks the entire database file during writes. We enabled **WAL (Write-Ahead Logging)** mode via `PRAGMA journal_mode = WAL;`. In WAL mode, writers append to a separate `-wal` file without blocking concurrent readers, enabling our background monitoring daemon to record periodic test runs while the frontend dashboard reads historical telemetry simultaneously."*

#### Q9: "Why use native ping subprocess instead of raw sockets (`socket.SOCK_RAW`)?"
> **Model Answer:**
> *"On Windows, opening a raw socket with `socket.SOCK_RAW` requires Administrator privileges (elevated command prompt). If the application relied on raw sockets, ordinary users could not execute it without elevation, and it would raise `PermissionError` (Windows socket error 10013).
> Executing the operating system's native `ping` utility via `subprocess.run(shell=False)` with regex parsing provides accurate kernel-timed measurements without requiring admin privileges, maintaining security and cross-platform portability."*

#### Q10: "How do you protect against shell injection attacks when executing ping?"
> **Model Answer:**
> *"We apply two layers of defense:
> 1. **Strict Input Validation:** Targets are matched against `^[a-zA-Z0-9\.\-:]+$` before execution. Any string containing spaces, semicolons, backticks, or shell metacharacters (`&`, `|`, `$`) is immediately rejected.
> 2. **Process Execution Safety:** We pass arguments as a list of strings (`["ping", "-4", "-n", str(count), target]`) with `shell=False`. This prevents the operating system shell from interpreting command separators or chaining arbitrary executables."*

#### Q11: "How did you prevent race conditions and deadlocks in the monitoring service?"
> **Model Answer:**
> *"The `MonitoringService` manages a background daemon thread. We utilized a re-entrant lock (`threading.RLock`) rather than a simple `threading.Lock`. 
> A standard lock deadlocks if a thread holding the lock calls another internal method that also requests the lock (such as `get_status()` calling locked internal properties). `RLock` tracks ownership and recursion depth. Additionally, thread startup (`self._thread.start()`) is intentionally executed outside the lock critical section to avoid lock inversion during thread initialization."*

#### Q12: "How does your test suite validate disconnected states without physically unplugging network cables?"
> **Model Answer:**
> *"In `tests/test_validation_scenarios.py`, we use Python's `unittest.mock.patch` to mock low-level system functions:
> - `get_default_gateway` is mocked to return `None`.
> - `run_ping_test` is mocked to return 100% loss and 'Destination host unreachable'.
> - `measure_dns_lookup` and `measure_tcp_connect` are mocked to raise network unreachable socket errors.
> This allows us to deterministically test every edge-case code path, verifying that the diagnostic engine categorizes the failure as `RULE_ALL_DESTINATIONS_FAILED` with `overall_status == 'critical'` without throwing unhandled exceptions."*

---

## 🏆 4. Summary of Project Achievements

1. **Academic Rigor:** Built on RFC 792 (ICMP), RFC 793 (TCP), RFC 1035 (DNS), and RFC-standard consecutive jitter formulations.
2. **Deterministic Explainability:** 11 rule evaluators that never fabricate data and always present quantitative thresholds, causes, recommendations, and caveats.
3. **Multi-Layer Differential Isolation:** Direct hop-1 gateway detection separating Wi-Fi problems from ISP WAN routing problems.
4. **Production Architecture:** SQLite in WAL mode, Flask application factory pattern, thread-safe background daemon, and responsive glassmorphic UI.
5. **Rock-Solid Test Coverage:** 73 unit, integration, and failure-scenario tests passing with 100% success.
