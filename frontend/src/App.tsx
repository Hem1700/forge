import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { WorkerHealthBanner } from './components/WorkerHealthBanner'
import { Home } from './pages/Home'
import { Engagement } from './pages/Engagement'
import { FindingDetailPage } from './pages/FindingDetail'
import { PrintReport } from './pages/PrintReport'

export default function App() {
  return (
    <BrowserRouter>
      <WorkerHealthBanner />
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/engagement/:id" element={<Engagement />} />
        <Route path="/engagement/:engagementId/findings/:findingId" element={<FindingDetailPage />} />
        <Route path="/print/:engagementId" element={<PrintReport />} />
      </Routes>
    </BrowserRouter>
  )
}
