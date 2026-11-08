# AMRIN website user guide

AMRIN is a web console for viewing railway inspection alerts, sensor readings, and maintenance work. It is a monitoring and maintenance application; it does not control railway signalling or operate trains.

## Sign in and accounts

1. Open the AMRIN website URL provided by the administrator.
2. Sign in with your account. Use **Forgot password?** if password recovery is configured for your installation.
3. If you do not have an account, use **Create account** if signup is enabled. Worker accounts may need administrator approval before they can access the system.
4. Use the profile area to log out when finished.

The pages available depend on your role:

- **Administrator:** Command Center, Live Map, Alerts, Tasks, Hardware, and ML Model Demo. Administrators can review alerts, assign work, approve submitted repairs, and review pending worker signups.
- **Worker:** Assigned jobs and Live Map. Workers can view assigned tasks, update their task status, and submit repair evidence for review.

## Administrator workflow

### Command Center

The Command Center is the overview page for current operations. Use the city selector to scope views where available. Select an alert or use the S3 shortcut to open high-severity alerts. A `DEMO DATA` banner means the records and readings are simulated, not live device data.

### Alerts

1. Open **Alerts** and use the tabs and filters to find an alert. Search and severity/city filters narrow the list.
2. Select an alert to open its details, including location, evidence image (when available), sensor readings/fusion, history, and status.
3. Acknowledge a detected alert when it is ready for maintenance handling.
4. Assign a worker or change its priority from the alert actions or the Tasks workflow.
5. Use **False positive** only when review confirms the detection is not a defect. Resolve the alert when the repair is complete. Resolved and false-positive alerts remain available in the resolved/history views.

An alert is not a maintenance task. A task is the work record associated with an acknowledged alert.

### Tasks and worker review

1. Open **Tasks** and use the status filters to view work by stage.
2. Create a task from an acknowledged alert, then choose a worker from the available worker list. The worker list is city-scoped when alert and worker city information is available.
3. Track the assignment and task status from the task list/detail.
4. When a worker submits evidence and marks the repair ready for review, open the task and review the evidence.
5. Approve the task only after confirming the repair evidence. If the work is incomplete, leave it for follow-up according to the available review actions.

Signup approvals, when enabled, appear in the Tasks page. Approve or reject pending worker accounts there. Administrator accounts are created through the administrator provisioning process, not worker signup approval.

### Hardware

Open **Hardware** to inspect registered devices, component readings, device status, and recent sensor history. `NO DATA` or `MISSING_DATA` means the app has no recent reading for that component; it does not mean the sensor measured zero. Device online status depends on recent posts. Demo readings are explicitly labeled as simulated.

### ML Model Demo

1. Open **ML Model Demo**.
2. Select a registered camera device and upload a supported train image.
3. Run inference to view the detected crack boxes, confidence values, severity/result, and inference time returned by the backend.

The backend must have its vision dependencies and a valid `ML_MODEL_PATH` configured. This demo runs the server-side model; it does not train a model in the browser. The current detector predicts a crack class. Its S1/S2/S3 severity is supplied by application logic, so validate severity on representative images before relying on it. A no-detection result does not prove a track is safe.

### Live Map

Open **Live Map** to view trains/devices with available coordinates. Use the filters and **Fit All** controls to adjust the map. Items without usable coordinates cannot be placed accurately.

### Simulation

Administrators can open `/simulation/simulator` for the standalone decision-support simulator. Its train movement is visual playback; it is not a live signalling controller. Stored ESP32 readings can be selected as an input source when available. Do not use the simulator to control real railway equipment.

## Worker workflow

1. Sign in and open **Assigned jobs**.
2. Select an assigned task to see its alert summary, location, sensor readout, notes, and current status.
3. Accept/start the work and update the task status as the job progresses.
4. While the task is in progress, upload repair evidence using the evidence control. Use a clear, relevant image and avoid including personal or unrelated information.
5. Submit the task for review when work and evidence are complete.
6. Check the task for the administrator’s review result or follow-up.

Workers can access only the work available to their account and city scope enforced by the backend.

## Status and data interpretation

- **Detected alert:** a model or integration created a candidate defect record; it requires human review.
- **Acknowledged:** an operator has accepted the alert for handling.
- **Task:** maintenance work created for an acknowledged alert.
- **Awaiting review:** worker submitted completed work/evidence for administrator review.
- **Resolved/completed:** work or alert has been marked finished through its applicable workflow.
- **False positive:** the alert was reviewed and determined not to be a true defect.
- **NO DATA / STALE:** no recent value is available. Check device connectivity and incoming posts.
- **DEMO DATA:** simulated records; do not interpret them as readings from physical hardware.

Confidence is the model score for a particular detection, not the model’s overall accuracy. Evaluate the model against held-out, correctly labeled images before operational use.

## Troubleshooting

- **API unavailable:** confirm the FastAPI backend is running and the frontend API URL points to it. Check backend logs and `/docs` if enabled in that environment.
- **No devices/readings:** confirm the ESP32 device is registered, has a valid ingest key, has network access to the backend, and is posting the documented sensor/frame contract.
- **Camera inference unavailable:** check backend vision dependencies, configured model path, model file permissions, and backend logs.
- **Cannot see an alert/task:** verify role permissions, city scope, filters, and current status tab.
- **Cannot upload evidence:** check file type/size, task status, assignment, and API connectivity.
- **Password recovery does not arrive:** ask the administrator to check email/reset configuration or use the account recovery process configured for the installation.

## Known route limitation

The navigation includes a **Settings** entry, but the current `/settings` route redirects to the Command Center rather than a standalone settings page. Use the administrator-provided deployment configuration for system thresholds and other backend settings.
