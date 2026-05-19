import React from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import Layout from './components/Layout';
import AnomalyList from './pages/AnomalyList';
import StockList from './pages/StockList';
import Industry from './pages/Industry';
import Data from './pages/Data';

const App: React.FC = () => {
  return (
    <Router>
      <Layout>
        <Routes>
          <Route path="/" element={<AnomalyList />} />
          <Route path="/stock-list" element={<StockList />} />
          <Route path="/industry" element={<Industry />} />
          <Route path="/data" element={<Data />} />
        </Routes>
      </Layout>
    </Router>
  );
};

export default App;
