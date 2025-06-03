const express = require('express');
const app = express();

app.use(express.json());

app.get('/', (req, res) => {
  res.json({ 
    status: 'OK', 
    message: 'Retell Restaurant Agent - Working!',
    timestamp: new Date().toISOString()
  });
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
  console.log(`🚀 Server running on port ${PORT}`);
});
