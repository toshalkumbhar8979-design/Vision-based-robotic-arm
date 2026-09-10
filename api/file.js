// Vercel Serverless PDF & Document Storage Endpoint
// Path: api/file.js

export const config = {
  api: {
    bodyParser: {
      sizeLimit: '10mb'
    }
  }
};

export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  if (req.method === 'OPTIONS') {
    return res.status(200).end();
  }

  // GET /api/file?url=<raw_blob_url>&name=<filename>
  if (req.method === 'GET') {
    const { url, name } = req.query;
    if (!url) {
      return res.status(400).json({ error: 'Missing file url' });
    }

    try {
      const blobRes = await fetch(url);
      if (blobRes.ok) {
        const fileJson = await blobRes.json();
        if (fileJson && fileJson.dataUrl) {
          const matches = fileJson.dataUrl.match(/^data:(.+);base64,(.+)$/);
          if (matches) {
            const mimeType = matches[1];
            const base64Data = matches[2];
            const buffer = Buffer.from(base64Data, 'base64');

            res.setHeader('Content-Type', mimeType || 'application/pdf');
            res.setHeader('Content-Disposition', `attachment; filename="${name || fileJson.name || 'document.pdf'}"`);
            return res.status(200).send(buffer);
          }
        }
      }
    } catch (e) {
      return res.status(500).json({ error: 'Failed to fetch stored PDF file' });
    }
    return res.status(404).json({ error: 'PDF file not found' });
  }

  // POST /api/file - Store PDF binary in Vercel cloud store
  if (req.method === 'POST') {
    try {
      const { name, dataUrl } = req.body || {};
      if (!dataUrl) {
        return res.status(400).json({ error: 'Missing file dataUrl' });
      }

      // Store in cloud JSONBlob storage
      const storeRes = await fetch('https://jsonblob.com/api/jsonBlob', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, dataUrl })
      });

      if (storeRes.ok) {
        const locationHeader = storeRes.headers.get('Location');
        if (locationHeader) {
          const directFileUrl = `/api/file?url=${encodeURIComponent(locationHeader)}&name=${encodeURIComponent(name || 'document.pdf')}`;
          return res.status(200).json({ status: 'success', fileUrl: directFileUrl });
        }
      }
    } catch (e) {
      return res.status(500).json({ error: e.message });
    }
    return res.status(500).json({ error: 'Failed to store PDF file on Vercel backend' });
  }

  res.status(405).end();
}
