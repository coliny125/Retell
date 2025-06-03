const express = require('express');
const app = express();

app.use(express.json());

app.get('/', (req, res) => {
  res.json({ 
    status: 'OK', 
    message: 'Retell Restaurant Agent - Working!',
    port: process.env.PORT || 3000,
    timestamp: new Date().toISOString()
  });
});

app.get('/health', (req, res) => {
  res.json({ status: 'OK' });
});

// Railway requires listening on 0.0.0.0 and PORT environment variable
const PORT = process.env.PORT || 3000;
app.listen(PORT, "0.0.0.0", () => {
  console.log(`🚀 Server running on host 0.0.0.0 and port ${PORT}`);
});
