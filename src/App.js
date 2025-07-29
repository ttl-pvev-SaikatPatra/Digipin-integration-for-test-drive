import React, { useState, useEffect } from 'react';

// Set this to your backend host, e.g. https://your-backend.onrender.com
const API_URL = 'https://your-flask-backend-url';

export default function App() {
  const [form, setForm] = useState({ name: '', car: '', lat: '', lon: '', digipin: '' });
  const [bookings, setBookings] = useState([]);
  const [message, setMessage] = useState('');

  // Fetch bookings on load
  useEffect(() => { fetch(`${API_URL}/api/bookings`) .then(res => res.json()).then(setBookings); }, []);

  // Convert coordinates to DigiPIN
  const getDigiPIN = async () => {
    if (!form.lat || !form.lon) return setMessage('Enter lat/lon');
    setMessage('Fetching DigiPIN...');
    const res = await fetch(`${API_URL}/api/digipin/encode?latitude=${form.lat}&longitude=${form.lon}`);
    const data = await res.json();
    setForm(f => ({ ...f, digipin: data.digipin || '' }));
    setMessage(data.digipin ? 'DigiPIN found!' : 'Failed to get DigiPIN');
  };

  // Submit booking
  const submit = async e => {
    e.preventDefault();
    setMessage('Submitting...');
    const res = await fetch(`${API_URL}/api/bookings`, {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(form)
    });
    if (res.ok) {
      setMessage('Booking successful!');
      fetch(`${API_URL}/api/bookings`).then(res => res.json()).then(setBookings);
    } else {
      setMessage('Booking failed.');
    }
  };

  return (
    <div style={{ maxWidth: 500, margin: '0 auto', padding: 16, fontFamily: 'sans-serif' }}>
      <h2>Book a Test Drive</h2>
      <form onSubmit={submit}>
        <input required placeholder="Name" value={form.name}
          onChange={e => setForm(f => ({ ...f, name: e.target.value }))} /><br />
        <input required placeholder="Car Model" value={form.car}
          onChange={e => setForm(f => ({ ...f, car: e.target.value }))} /><br />
        <input required placeholder="Latitude" value={form.lat}
          onChange={e => setForm(f => ({ ...f, lat: e.target.value }))} /><br />
        <input required placeholder="Longitude" value={form.lon}
          onChange={e => setForm(f => ({ ...f, lon: e.target.value }))} /><br />
        <button type="button" onClick={getDigiPIN}>Get DigiPIN</button><br />
        <input placeholder="DigiPIN" value={form.digipin} readOnly /><br />
        <button type="submit">Book Test Drive</button>
      </form>
      <div>{message}</div>
      <h3>All Bookings</h3>
      <table><thead>
        <tr><th>Name</th><th>Car</th><th>DigiPIN</th></tr>
      </thead><tbody>
        {bookings.map((b, i) => <tr key={i}>
          <td>{b.name}</td>
          <td>{b.car}</td>
          <td>{b.digipin}</td>
        </tr>)}
      </tbody></table>
    </div>
  );
}
