const webpush = require('web-push');
const fs = require('fs');

const VAPID_PUBLIC_KEY = 'BJkHvvYMT828PZMYCyiPE2-7HAU5VXapiqaQNJ1P6vG1M9y_94jWRrMvBeYjEUHkS3KXbdHvwLBpnqPupT37-qw';
const VAPID_PRIVATE_KEY = process.env.VAPID_PRIVATE_KEY;

if (!VAPID_PRIVATE_KEY) {
  console.error('VAPID_PRIVATE_KEY secret is not set in GitHub Actions secrets');
  process.exit(1);
}

webpush.setVapidDetails('mailto:bot@coachclaudio.local', VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY);

const SPORT_LABELS = {
  running:'Run', cycling:'Ride', cycling_indoor:'Ride',
  strength:'Strength', swimming:'Swim', yoga:'Yoga',
  hiking:'Hike', walking:'Walk', rowing:'Row',
  elliptical:'Elliptical', tennis:'Tennis', skiing:'Ski',
  soccer:'Soccer', boxing:'Boxing',
};
const DAYS = ['Sunday','Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'];

function getTomorrow() {
  const t = new Date();
  t.setUTCDate(t.getUTCDate() + 1);
  return { name: DAYS[t.getUTCDay()], iso: t.toISOString().split('T')[0] };
}

function getTomorrowSessions() {
  const tomorrow = getTomorrow();
  let plan = [];
  try { plan = JSON.parse(fs.readFileSync('weekly_plan.json', 'utf8')); } catch(e) {}
  return { sessions: plan.filter(s => s.day === tomorrow.name || s.date === tomorrow.iso), dayName: tomorrow.name };
}

function formatNotification(sessions, dayName) {
  if (!sessions.length) {
    return { title: `Coach Claudio — ${dayName}`, body: 'Rest day tomorrow. Recovery is training too 💤' };
  }
  const parts = sessions.map(s => {
    const sport = SPORT_LABELS[s.sport] || (s.sport || 'Session');
    const dur = s.total_duration_secs ? Math.round(s.total_duration_secs / 60) : null;
    return dur ? `${s.name || sport} (${dur} min)` : (s.name || sport);
  });
  const tss = sessions.reduce((sum, s) => sum + (s.planned_tss || 0), 0);
  return {
    title: `Coach Claudio — ${dayName}`,
    body: parts.join(' · ') + (tss ? `  ·  ${Math.round(tss)} TSS` : ''),
  };
}

async function main() {
  let subs = [];
  try { subs = JSON.parse(fs.readFileSync('push_subscriptions.json', 'utf8')); } catch(e) {}
  if (!subs.length) { console.log('No push subscriptions — nothing to send'); return; }

  const { sessions, dayName } = getTomorrowSessions();
  const { title, body } = formatNotification(sessions, dayName);
  console.log(`Sending: ${title}\n         ${body}`);

  const payload = JSON.stringify({ title, body });
  const failed = [];

  for (const sub of subs) {
    try {
      await webpush.sendNotification(sub, payload);
      console.log(`  ✓ ${sub.endpoint.substring(0, 60)}…`);
    } catch(e) {
      if (e.statusCode === 404 || e.statusCode === 410) {
        console.log(`  ✗ expired (${e.statusCode}), removing`);
        failed.push(sub.endpoint);
      } else {
        console.error(`  ✗ failed: ${e.message} (HTTP ${e.statusCode || '?'})`);
      }
    }
  }

  if (failed.length) {
    const updated = subs.filter(s => !failed.includes(s.endpoint));
    fs.writeFileSync('push_subscriptions.json', JSON.stringify(updated, null, 2));
    console.log(`Removed ${failed.length} expired subscription(s)`);
  }
}

main().catch(e => { console.error(e); process.exit(1); });
