from pathlib import Path
root=Path(__file__).resolve().parents[1]
h=(root/'static/index.html').read_text(); j=(root/'static/app.js').read_text(); m=(root/'app/main.py').read_text(); c=(root/'static/style.css').read_text()
for needle in ['id="dashPeriod"','id="dashboardYearView"','id="dashboardYearChart"','id="planningPeriod"','id="planningYearView"','id="auditTimeline"']:
 assert needle in h,needle
for needle in ['loadDashboardYear','loadPlanningYear','loadAuditTimeline','formatAuditTimestamp']:
 assert needle in j,needle
assert '/api/audit/timeline' in m and '/api/dashboard/year' in m
assert 'audit-timeline' in c
print('v0.8.2 source requirements: PASS')
