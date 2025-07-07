import { useState } from 'react';
import axios from 'axios';

function App() {
  const [prompt, setPrompt] = useState('');
  const [formData, setFormData] = useState(null);
  const [error, setError] = useState('');

  const handleGenerate = async () => {
    setError('');
    setFormData(null);

    try {
      const res = await axios.post('http://127.0.0.1:5000/generate-form', { prompt });
      setFormData(res.data);
    } catch (err) {
      if (err.response && err.response.data && err.response.data.error) {
        setError(err.response.data.error);
      } else {
        setError('Failed to connect to backend.');
      }
    }
  };

  return (
    <div style={{ padding: '2rem', fontFamily: 'sans-serif' }}>
      <h1>AI Form Generator</h1>

      <textarea
        rows="4"
        cols="50"
        placeholder="Enter prompt to generate form..."
        value={prompt}
        onChange={(e) => setPrompt(e.target.value)}
      />
      <br /><br />

      <button onClick={handleGenerate}>Generate Form</button>
      <br /><br />

      {error && <p style={{ color: 'red' }}>❌ {error}</p>}

      {formData && (
        <div>
          <h2>{formData.title}</h2>
          <form>
            {formData.fields.map((field, idx) => (
              <div key={idx} style={{ marginBottom: '1rem' }}>
                <label>{field.label}:</label><br />
                <input type={field.type} name={field.label.toLowerCase()} />
              </div>
            ))}
          </form>
        </div>
      )}
    </div>
  );
}

export default App;
