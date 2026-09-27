import streamlit as st
import pandas as pd
import pydeck as pdk
import json
import os
import math
import random
from datetime import datetime, timezone, timedelta
from streamlit_autorefresh import st_autorefresh

# 1. Page Configuration
st.set_page_config(page_title="DUET Campus Transit & Grievance Portal", layout="wide", initial_sidebar_state="expanded")
st_autorefresh(interval=5000, key="duet_fleet_refresh")

# 2. Karachi Pakistan Time (PKT = UTC+5)
PKT_TZ = timezone(timedelta(hours=5))
now_pkt = datetime.now(PKT_TZ)
current_time_str = now_pkt.strftime("%I:%M:%S %p")
today_date_str = now_pkt.strftime("%Y-%m-%d")

# 3. Load Fleet Routes from routes_config.json
if not os.path.exists("routes_config.json"):
    st.error("⚠️ `routes_config.json` file nahi mili! Tasdeeq karein ke file isi folder mein save hai.")
    st.stop()

with open("routes_config.json", "r") as f:
    try:
        ROUTES_DATA = json.load(f)
    except Exception as e:
        st.error(f"routes_config.json read karne mein masla hua: {e}")
        st.stop()

# 4. Custom Cyber UI Styling
st.markdown("""
<style>
    .main { background: #070b14; color: #f8fafc; font-family: 'Segoe UI', Tahoma, sans-serif; }
    .duet-header {
        background: linear-gradient(135deg, rgba(15, 23, 42, 0.95), rgba(30, 41, 59, 0.85));
        border: 1px solid rgba(56, 189, 248, 0.25);
        padding: 20px 26px; border-radius: 16px; margin-bottom: 20px;
        display: flex; justify-content: space-between; align-items: center;
    }
    .duet-title { font-size: 22px; font-weight: 800; color: #ffffff; }
    .duet-sub { font-size: 13px; color: #94a3b8; }
    .pulse-badge {
        display: inline-flex; align-items: center; gap: 8px;
        background: rgba(34, 197, 94, 0.15); border: 1px solid #22c55e;
        color: #4ade80; padding: 6px 14px; border-radius: 20px; font-weight: 700; font-size: 12px;
    }
    .pulse-dot { width: 9px; height: 9px; background: #22c55e; border-radius: 50%; box-shadow: 0 0 10px #22c55e; }
    .kpi-card {
        background: rgba(15, 23, 42, 0.8); border: 1px solid rgba(255,255,255,0.08);
        border-radius: 14px; padding: 16px 18px; text-align: left;
    }
    .kpi-title { font-size: 11px; text-transform: uppercase; color: #64748b; font-weight: 700; }
    .kpi-val { font-size: 24px; font-weight: 800; color: #38bdf8; margin-top: 4px; }
    .stop-row {
        display: flex; align-items: center; justify-content: space-between;
        padding: 10px 15px; margin-bottom: 7px; border-radius: 10px;
        background: rgba(15, 23, 42, 0.6); border: 1px solid rgba(255,255,255,0.05); font-size: 13px;
    }
    .stop-active { border-left: 6px solid #22c55e !important; background: rgba(34, 197, 94, 0.15) !important; }
    .stop-passed { border-left: 6px solid #ef4444 !important; opacity: 0.5; }
    .stop-upcoming { border-left: 6px solid #eab308 !important; }
    .status-pill { font-weight: 700; padding: 4px 10px; border-radius: 6px; font-size: 10px; }
    .card-box {
        background: rgba(15, 23, 42, 0.7); border: 1px solid rgba(255,255,255,0.08);
        border-radius: 12px; padding: 18px; margin-bottom: 15px;
    }
</style>
""", unsafe_allow_html=True)

# 5. Helper Distance Function (Haversine km)
def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))

# 6. Sidebar Controls
with st.sidebar:
    st.markdown("### 🚎 Select DUET Point")
    keys = list(ROUTES_DATA.keys())
    labels = [f"{ROUTES_DATA[k]['point_no']} ({ROUTES_DATA[k]['vehicle_no']})" for k in keys]
    selected_idx = st.selectbox("Active Point View", range(len(keys)), format_func=lambda x: labels[x])
    selected_key = keys[selected_idx]
    active_point = ROUTES_DATA[selected_key]
    
    st.markdown("---")
    st.markdown("### 📋 Assigned Driver Details")
    st.write(f"**Driver:** {active_point['driver_name']}")
    st.write(f"**Point No:** `{active_point['point_no']}`")
    st.write(f"**Vehicle Reg:** `{active_point['vehicle_no']}`")
    st.markdown(f'<a href="tel:{active_point["driver_phone"]}" style="display:inline-block; background:#0284c7; color:#ffffff; padding:7px 12px; border-radius:8px; text-decoration:none; font-weight:700; font-size:12px;">📞 Call Driver ({active_point["driver_phone"]})</a>', unsafe_allow_html=True)
    st.markdown("---")
    st.caption("• **Campus Arrival:** `08:30 AM`\n• **Campus Departure:** `05:00 PM`")
    st.info("💡 **Daily Reset:** Raat 12:00 AM par tamam stops khud ba khud **Upcoming** par shift ho jate hain.")

# 7. Live Telemetry Read
# app.py ke Section 7 mein yeh hona chahiye:
FIREBASE_DB_URL = "https://duet-transit-sa-ui-default-rtdb.firebaseio.com"

try:
    url = f"{FIREBASE_DB_URL}/live_fleet/{selected_key}.json"
    resp = requests.get(url, timeout=3)
    if resp.status_code == 200 and resp.json():
        live = resp.json()
        bus_lat = float(live.get("lat", 0.0))
        bus_lon = float(live.get("lon", 0.0))
        bus_speed = float(live.get("speed", 0.0))
        last_timestamp = live.get("timestamp", "N/A")
except Exception:
    pass

# 8. Midnight Reset Engine (Per-Point State)
state_file = f"daily_state_{selected_key}.json"
state = {"date": today_date_str, "passed_stops": []}
if os.path.exists(state_file):
    try:
        with open(state_file, "r") as f:
            saved = json.load(f)
            if saved.get("date") == today_date_str:
                state = saved
    except Exception:
        pass

passed_stops_set = set(state.get("passed_stops", []))
stops = active_point["stops"]
closest_idx = None
min_dist = float("inf")

if bus_lat != 0.0 and bus_lon != 0.0:
    for idx, s in enumerate(stops):
        d = haversine(bus_lat, bus_lon, s["lat"], s["lon"])
        if d < min_dist:
            min_dist = d
            closest_idx = idx

    if closest_idx is not None and min_dist <= 1.0:
        for prev_i in range(closest_idx):
            passed_stops_set.add(stops[prev_i]["stop_id"])
    elif closest_idx is not None and min_dist > 1.0 and closest_idx > 0:
        for prev_i in range(closest_idx):
            passed_stops_set.add(stops[prev_i]["stop_id"])

state["passed_stops"] = list(passed_stops_set)
state["date"] = today_date_str
with open(state_file, "w") as f:
    json.dump(state, f)

# 9. Format Stops Data
processed_stops = []
for idx, s in enumerate(stops):
    sid = s["stop_id"]
    d = haversine(bus_lat, bus_lon, s["lat"], s["lon"]) if (bus_lat != 0.0 and bus_lon != 0.0) else 0.0
    
    if idx == closest_idx and min_dist <= 1.0:
        status, css, rgb = "ARRIVING / NEAR", "stop-active", [34, 197, 94, 255]
    elif sid in passed_stops_set:
        status, css, rgb = "DEPARTED", "stop-passed", [239, 68, 68, 220]
    else:
        status, css, rgb = "UPCOMING", "stop-upcoming", [234, 179, 8, 220]
        
    processed_stops.append({**s, "dist": d, "status": status, "css": css, "rgb": rgb})

upcoming = [s for s in processed_stops if s["status"] != "DEPARTED"]
target_name = upcoming[0]["name"] if upcoming else active_point["campus"]
target_dist = upcoming[0]["dist"] if upcoming else 0.0
est_speed = max(bus_speed, 18.0)
eta_mins = round((target_dist / est_speed) * 60)
eta_str = (now_pkt + timedelta(minutes=eta_mins)).strftime("%I:%M %p")

# 10. Live University Header
st.markdown(f"""
<div class='duet-header'>
    <div>
        <div class='duet-title'>🏛️ DAWOOD UNIVERSITY OF ENGINEERING & TECHNOLOGY</div>
        <div class='duet-sub'>Transport Section • Live Campus Transit & Student Grievance Portal</div>
    </div>
    <div style='text-align: right;'>
        <div class='pulse-badge'><span class='pulse-dot'></span> LIVE TELEMETRY • PKT {current_time_str}</div>
        <div style='color: #64748b; font-size: 11px; margin-top: 5px;'>Active Fleet: <b>{active_point['point_no']}</b> ({active_point['vehicle_no']})</div>
    </div>
</div>
""", unsafe_allow_html=True)

# 11. Main Navigation Tabs
tab_radar, tab_feedback, tab_complaint = st.tabs([
    "🗺️ Live Transit Radar", 
    "⭐ Driver Ratings & Feedback (Public)", 
    "⚠️ Driver Complaint & Grievance (Confidential)"
])

# ================= TAB 1: RADAR & STOPS =================
with tab_radar:
    c1, c2, c3, c4 = st.columns(4)
    c1.markdown(f"<div class='kpi-card'><div class='kpi-title'>Live Speed</div><div class='kpi-val'>{bus_speed} <span style='font-size:14px; color:#64748b;'>km/h</span></div></div>", unsafe_allow_html=True)
    c2.markdown(f"<div class='kpi-card'><div class='kpi-title'>Next Target Stop</div><div class='kpi-val' style='font-size:18px; color:#38bdf8;'>{target_name}</div></div>", unsafe_allow_html=True)
    c3.markdown(f"<div class='kpi-card'><div class='kpi-title'>Distance to Target</div><div class='kpi-val'>{target_dist:.2f} <span style='font-size:14px; color:#64748b;'>km</span></div></div>", unsafe_allow_html=True)
    c4.markdown(f"<div class='kpi-card'><div class='kpi-title'>Estimated Arrival</div><div class='kpi-val' style='color:#f59e0b;'>{eta_str} <span style='font-size:13px; color:#64748b;'>({eta_mins}m)</span></div></div>", unsafe_allow_html=True)

    st.write("")
    map_col, list_col = st.columns([1.7, 1.2])

    with map_col:
        st.subheader(f"🗺️ Route Radar — {active_point['route_name']}")
        stops_df = pd.DataFrame(processed_stops)
        bus_df = pd.DataFrame([{"lat": bus_lat, "lon": bus_lon, "name": active_point["point_no"]}])
        route_path = [{"path": [[s["lon"], s["lat"]] for s in stops], "color": [56, 189, 248, 140]}]
        
        layers = [
            pdk.Layer("PathLayer", data=route_path, get_path="path", get_color="color", width_min_pixels=3, rounded=True),
            pdk.Layer("ScatterplotLayer", data=stops_df, get_position=["lon", "lat"], get_color="rgb", get_radius=110, pickable=True),
            pdk.Layer("ScatterplotLayer", data=bus_df, get_position=["lon", "lat"], get_color=[244, 63, 94, 255], get_radius=220, pickable=True)
        ]
        center_lat = bus_lat if bus_lat != 0.0 else stops[0]["lat"]
        center_lon = bus_lon if bus_lon != 0.0 else stops[0]["lon"]
        st.pydeck_chart(pdk.Deck(layers=layers, initial_view_state=pdk.ViewState(latitude=center_lat, longitude=center_lon, zoom=12.4, pitch=35), map_style="dark"))

    with list_col:
        st.subheader("📍 Geofence Stops Status")
        st.caption("🟢 Green: Reaching (< 1km) | 🔴 Red: Departed | 🟡 Yellow: Upcoming")
        scroll_area = st.container(height=480)
        with scroll_area:
            for s in processed_stops:
                pill_color = "#22c55e" if "ARRIVING" in s["status"] else ("#ef4444" if "DEPARTED" in s["status"] else "#eab308")
                scroll_area.markdown(f"""
                <div class='stop-row {s["css"]}'>
                    <div><b>#{s['stop_id']} {s['name']}</b><br><small style='color:#64748b;'>Fasla: {s['dist']:.2f} km</small></div>
                    <div class='status-pill' style='background:{pill_color}; color:#000000;'>{s['status']}</div>
                </div>
                """, unsafe_allow_html=True)

# ================= TAB 2: PUBLIC DRIVER FEEDBACK =================
with tab_feedback:
    st.subheader("⭐ Public Driver Ratings & Student Experience")
    st.caption("Tamam students ka feedback yahan publicly display hota hai taake drivers ki overall service monitor ho sake.")

    feedbacks = []
    if os.path.exists("feedback.json"):
        try:
            with open("feedback.json", "r") as ff:
                feedbacks = json.load(ff)
        except Exception:
            pass

    col_fb_form, col_fb_list = st.columns([1.2, 1.8])

    with col_fb_form:
        st.markdown(f"#### Rate Driver: **{active_point['driver_name']}** ({active_point['point_no']})")
        with st.form("feedback_form", clear_on_submit=True):
            fb_student_name = st.text_input("Your Name / Department (Optional)", placeholder="e.g. Ali - AI 5th Sem")
            fb_rating = st.slider("Rating (1 = Poor, 5 = Excellent)", min_value=1, max_value=5, value=5)
            fb_comment = st.text_area("Write your feedback / experience", placeholder="Point hamesha time par hota hai, driver ka behavior kaisa raha...")
            submit_fb = st.form_submit_button("Submit Public Feedback")

            if submit_fb:
                new_entry = {
                    "point_no": active_point["point_no"],
                    "driver_name": active_point["driver_name"],
                    "student": fb_student_name if fb_student_name else "Anonymous DUET Student",
                    "rating": fb_rating,
                    "comment": fb_comment,
                    "date": now_pkt.strftime("%d %b %Y, %I:%M %p")
                }
                feedbacks.insert(0, new_entry)
                with open("feedback.json", "w") as ff:
                    json.dump(feedbacks, ff)
                st.success("Aapka feedback publicly submit ho gaya hai!")

    with col_fb_list:
        st.markdown(f"#### Recent Student Reviews for {active_point['point_no']}")
        point_feedbacks = [f for f in feedbacks if f.get("point_no") == active_point["point_no"]]
        
        if point_feedbacks:
            avg_rating = sum([f["rating"] for f in point_feedbacks]) / len(point_feedbacks)
            st.metric("Driver Average Rating", f"⭐ {avg_rating:.1f} / 5.0", f"{len(point_feedbacks)} Reviews")
            st.write("---")
            fb_container = st.container(height=420)
            with fb_container:
                for f in point_feedbacks:
                    stars = "⭐" * int(f["rating"])
                    fb_container.markdown(f"""
                    <div class='card-box'>
                        <div style='display:flex; justify-content:space-between;'>
                            <b>{f['student']}</b>
                            <span style='color:#f59e0b;'>{stars}</span>
                        </div>
                        <p style='color:#cbd5e1; margin-top:6px; font-size:13px;'>"{f['comment']}"</p>
                        <small style='color:#64748b;'>{f['date']}</small>
                    </div>
                    """, unsafe_allow_html=True)
        else:
            st.info(f"Abhi tak {active_point['point_no']} ke liye koi review nahi aaya. Aap pehla review submit karein!")

# ================= TAB 3: CONFIDENTIAL COMPLAINTS & GRIEVANCE =================
with tab_complaint:
    st.subheader("⚠️ Driver & Transit Complaint Portal")
    st.caption("🔒 **Strict Privacy:** Complaints sirf **concerned student** aur **DUET Transport Section** ko dikhayi deti hain.")

    complaints = []
    if os.path.exists("complaints.json"):
        try:
            with open("complaints.json", "r") as cf:
                complaints = json.load(cf)
        except Exception:
            pass

    col_cmp_submit, col_cmp_track = st.columns([1.5, 1.5])

    # Left: Complaint Submission Form
    with col_cmp_submit:
        st.markdown("#### 📝 File a Driver Complaint")
        with st.form("driver_complaint_form", clear_on_submit=True):
            student_roll = st.text_input("Your Roll Number (Required for Tracking)", placeholder="e.g. 22-AI-45")
            student_contact = st.text_input("Your Contact / WhatsApp (Optional)", placeholder="03xx-xxxxxxx")
            
            cmp_point = st.selectbox("Select Point", [f"{ROUTES_DATA[k]['point_no']} - {ROUTES_DATA[k]['driver_name']}" for k in ROUTES_DATA.keys()])
            
            selected_issues = st.multiselect(
                "Select Issues / Violations (Multiple Choices Available)",
                options=[
                    "Over-speeding / Rash & Dangerous Driving",
                    "Skipped Designated Student Stop",
                    "Unscheduled Delay / Not leaving on time",
                    "Rude Behavior / Verbal Misconduct by Driver/Conductor",
                    "Overloading / Refused to allow students inside",
                    "Using Mobile Phone while Driving",
                    "Bus Hygiene / Broken Windows / Cleanliness Issue",
                    "Dropped students away from safe stop"
                ],
                default=["Over-speeding / Rash & Dangerous Driving"]
            )
            
            cmp_explanation = st.text_area("Explain your complaint in detail", placeholder="Waqia kab aur kis chowrangi/stop par pesh aaya? Driver ne kya kiya...")
            submit_cmp = st.form_submit_button("🚨 Submit Confidential Complaint")

            if submit_cmp:
                if not student_roll:
                    st.error("Roll Number likhna lazmi hai taake aap apni complaint ka status track kar sakein.")
                elif not selected_issues:
                    st.error("Kam az kam ek issue category select karein.")
                else:
                    ticket_id = f"DUET-CMP-{random.randint(1000, 9999)}"
                    complaint_record = {
                        "ticket_id": ticket_id,
                        "roll_no": student_roll.strip().upper(),
                        "contact": student_contact,
                        "point_driver": cmp_point,
                        "issues": selected_issues,
                        "explanation": cmp_explanation,
                        "status": "Under Review",
                        "admin_remark": "Complaint received. Transport officer is verifying telemetry logs.",
                        "timestamp": now_pkt.strftime("%d %b %Y, %I:%M %p")
                    }
                    complaints.insert(0, complaint_record)
                    with open("complaints.json", "w") as cf:
                        json.dump(complaints, cf)
                    st.success(f"Complaint darj ho gayi! Aapki Ticket ID: **{ticket_id}** hai.")
                    st.info("Is Ticket ID ya apne Roll Number se aap barabar wale box mein status track kar sakte hain.")

    # Right: Individual Student Status Tracking
    with col_cmp_track:
        st.markdown("#### 🔍 Student Private Tracking Status")
        track_query = st.text_input("Enter your Roll No or Ticket ID to Check Status", placeholder="e.g. 22-AI-45 or DUET-CMP-1234")
        
        if track_query:
            query = track_query.strip().upper()
            student_records = [c for c in complaints if c.get("roll_no") == query or c.get("ticket_id") == query]
            
            if student_records:
                st.write(f"Showing **{len(student_records)}** record(s) matching `{query}`:")
                for rec in student_records:
                    status_col = "#eab308" if rec["status"] == "Under Review" else ("#38bdf8" if rec["status"] == "In Progress" else "#22c55e")
                    st.markdown(f"""
                    <div class='card-box' style='border-left: 6px solid {status_col};'>
                        <div style='display:flex; justify-content:space-between;'>
                            <b>Ticket: {rec['ticket_id']}</b>
                            <span style='background:{status_col}; color:#000; font-weight:700; padding:2px 8px; border-radius:4px; font-size:11px;'>{rec['status']}</span>
                        </div>
                        <div style='margin-top:6px; font-size:13px;'>
                            <b>Point / Driver:</b> {rec['point_driver']}<br>
                            <b>Issues Reported:</b> {", ".join(rec['issues'])}<br>
                            <b>Your Note:</b> <i>"{rec['explanation']}"</i>
                        </div>
                        <div style='margin-top:10px; background:rgba(0,0,0,0.3); padding:8px 12px; border-radius:6px; font-size:12px; border:1px dashed #64748b;'>
                            🛡️ <b>Transport Office Note:</b> {rec.get('admin_remark', 'Verification under process.')}
                        </div>
                        <small style='color:#64748b; display:block; margin-top:6px;'>Reported On: {rec['timestamp']}</small>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.warning("Is Roll Number ya Ticket ID par koi complaint record mojood nahi hai.")
        else:
            st.info("Apna status janne ke liye upar Roll No ya Ticket ID likhein.")

    # Bottom: Secured University Transport Department Section
    st.write("---")
    with st.expander("🔐 DUET Transport Department Official Access (Admin Only)"):
        admin_pass = st.text_input("Enter Transport Officer Secret Passkey", type="password")
        if admin_pass == "987654321duet":
            st.success("Authorized: DUET Transport Section Grievance Management Panel Active.")
            
            if complaints:
                cmp_df = pd.DataFrame(complaints)
                st.write(f"Total Complaints Registered: **{len(complaints)}**")
                
                col_adm_sel, col_adm_act, col_adm_note = st.columns([1, 1, 2])
                with col_adm_sel:
                    ticket_to_update = st.selectbox("Select Ticket ID", [c["ticket_id"] for c in complaints])
                with col_adm_act:
                    new_status = st.selectbox("Update Status", ["Under Review", "In Progress", "Resolved"])
                with col_adm_note:
                    officer_remark = st.text_input("Official Remarks / Action Taken", placeholder="Driver warned / route inspected...")
                
                if st.button("Save Official Action"):
                    for c in complaints:
                        if c["ticket_id"] == ticket_to_update:
                            c["status"] = new_status
                            if officer_remark:
                                c["admin_remark"] = officer_remark
                    with open("complaints.json", "w") as cf:
                        json.dump(complaints, cf)
                    st.success(f"Ticket {ticket_to_update} successfully updated to '{new_status}'!")
                    st.rerun()

                st.dataframe(cmp_df[["ticket_id", "roll_no", "point_driver", "issues", "status", "timestamp"]])
            else:
                st.info("Transport office ke paas filhal koi nayi complaint registered nahi hai.")
        elif admin_pass != "":
            st.error("Ghalat Passkey! Sirf authorized officers access kar sakte hain.")

st.caption(f"Last Sensor Ping: `{last_timestamp}` | Gateway: SSL Encrypted Tunnel | DUET Transport Section Karachi")
