import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { Home } from './pages/Home'
import { Engagement } from './pages/Engagement'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/engagement/:id" element={<Engagement />} />
      </Routes>
    </BrowserRouter>
  )
}
