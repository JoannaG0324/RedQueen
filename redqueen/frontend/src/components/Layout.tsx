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
              { key: '/', label: <Link to="/">Anomaly List of Stocks</Link> },
            ]}
          />
        </Space>
      </Header>
      <Content style={{ padding: '24px' }}>
        {children}
      </Content>
      <Footer style={{ textAlign: 'center' }}>
        RedQueen Investment ©{new Date().getFullYear()} Created by Trae AI
      </Footer>
    </AntLayout>
  );
};

export default Layout;
