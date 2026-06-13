import React, { ReactNode } from 'react';
import { Layout as AntLayout, Menu, Typography, Space } from 'antd';
import { Link, useLocation } from 'react-router-dom';

const { Header, Content, Footer } = AntLayout;
const { Title, Text } = Typography;

interface LayoutProps {
  children: ReactNode;
}

const Layout: React.FC<LayoutProps> = ({ children }) => {
  const location = useLocation();

  return (
    <AntLayout style={{ minHeight: '100vh' }}>
      <Header style={{ background: '#fff', padding: '0 24px' }}>
        <Space size="middle" style={{ width: '100%', justifyContent: 'space-between', alignItems: 'center' }}>
          <Title level={4} style={{ margin: 0, color: '#1890ff' }}>
            RedQueen Investment
          </Title>
          <Menu
            mode="horizontal"
            selectedKeys={[location.pathname]}
            items={[
              { key: '/', label: <Link to="/">Heatmap</Link> },
              { key: '/industry', label: <Link to="/industry">Industry</Link> },
              { key: '/stock-list', label: <Link to="/stock-list">Stock</Link> },
              { key: '/anomaly', label: <Link to="/anomaly">Anomaly</Link> },
              { key: '/data', label: <Link to="/data">Data</Link> },
            ]}
          />
        </Space>
      </Header>
      <Content style={{ padding: '24px', width: '100%', maxWidth: '100%', flex: 1, display: 'flex' }}>
        <div style={{ width: '100%', height: '100%' }}>
          {children}
        </div>
      </Content>
      <Footer style={{ textAlign: 'center' }}>
        RedQueen Investment ©{new Date().getFullYear()} Created by Trae AI
      </Footer>
    </AntLayout>
  );
};

export default Layout;
