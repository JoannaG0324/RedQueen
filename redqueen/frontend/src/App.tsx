import React from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import Layout from './components/Layout';
import AnomalyList from './pages/AnomalyList';

const App: React.FC = () => {
  return (
    <Router>
      <Layout>
        <Routes>
          <Route path="/" element={<AnomalyList />} />
        </Routes>
      </Layout>
    </Router>
  );
};

export default App;
