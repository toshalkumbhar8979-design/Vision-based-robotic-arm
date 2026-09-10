// Vercel Serverless API Endpoint with Supabase PostgreSQL Persistence
// Path: api/journal.js

const SUPABASE_URL = 'https://pzewxynfhrylnqbkkeeq.supabase.co';
const SUPABASE_KEY = 'sb_publishable_5OpuR0lsXoop77YXHtP01g_owDDLGe_';

export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, PUT, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type, apikey, Authorization');

  if (req.method === 'OPTIONS') {
    return res.status(200).end();
  }

  const endpoint = `${SUPABASE_URL}/rest/v1/journal_entries`;

  if (req.method === 'GET') {
    try {
      const response = await fetch(`${endpoint}?select=*&order=created_at.desc`, {
        headers: {
          'apikey': SUPABASE_KEY,
          'Authorization': `Bearer ${SUPABASE_KEY}`
        }
      });

      if (response.ok) {
        const data = await response.json();
        if (Array.isArray(data)) {
          return res.status(200).json(data);
        }
      }
    } catch (e) {}

    return res.status(200).json([]);
  }

  if (req.method === 'POST' || req.method === 'PUT') {
    const bodyData = req.body;
    let payload = null;

    if (Array.isArray(bodyData)) {
      payload = bodyData;
    } else if (bodyData && Array.isArray(bodyData.entries)) {
      payload = bodyData.entries;
    } else if (bodyData && bodyData.id) {
      payload = [bodyData];
    }

    if (!payload) {
      return res.status(400).json({ error: 'Missing or invalid entries payload' });
    }

    try {
      const response = await fetch(endpoint, {
        method: 'POST',
        headers: {
          'apikey': SUPABASE_KEY,
          'Authorization': `Bearer ${SUPABASE_KEY}`,
          'Content-Type': 'application/json',
          'Prefer': 'resolution=merge-duplicates,return=representation'
        },
        body: JSON.stringify(payload)
      });

      if (response.ok) {
        const saved = await response.json();
        return res.status(200).json({ status: 'saved', count: saved.length, data: saved });
      } else {
        const errText = await response.text();
        return res.status(500).json({ error: errText });
      }
    } catch (err) {
      return res.status(500).json({ error: err.message });
    }
  }

  res.status(405).end();
}
