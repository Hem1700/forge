import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { Home } from './pages/Home'
import { Engagement } from './pages/Engagement'
import { FindingDetailPage } from './pages/FindingDetail'
import { PrintReport } from './pages/PrintReport'
import { Login } from './pages/Login'
import { Profile } from './pages/Profile'
import { OrgSettings } from './pages/OrgSettings'
import { AdminPanel } from './pages/AdminPanel'
import { ProtectedRoute } from './components/ProtectedRoute'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/" element={<ProtectedRoute><Home /></ProtectedRoute>} />
        <Route path="/engagement/:id" element={<ProtectedRoute><Engagement /></ProtectedRoute>} />
        <Route
          path="/engagement/:engagementId/findings/:findingId"
          element={<ProtectedRoute><FindingDetailPage /></ProtectedRoute>}
        />
        <Route path="/print/:engagementId" element={<ProtectedRoute><PrintReport /></ProtectedRoute>} />
        <Route path="/profile" element={<ProtectedRoute><Profile /></ProtectedRoute>} />
        <Route
          path="/org/settings"
          element={<ProtectedRoute requireRole="admin"><OrgSettings /></ProtectedRoute>}
        />
        <Route
          path="/admin"
          element={<ProtectedRoute requireRole="super_admin"><AdminPanel /></ProtectedRoute>}
        />
      </Routes>
    </BrowserRouter>
  )
}
