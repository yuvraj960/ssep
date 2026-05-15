import React from 'react';
import { NavigationContainer } from '@react-navigation/native';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { DashboardScreen } from '../screens/DashboardScreen';

export type RootTabParamList = {
  Home: undefined;
};

const Tab = createBottomTabNavigator<RootTabParamList>();

export const AppNavigator: React.FC = () => {
  return (
    <NavigationContainer>
      <Tab.Navigator
        screenOptions={{
          headerStyle: { backgroundColor: '#1E1E1E' },
          headerTintColor: '#FFF',
          tabBarStyle: { backgroundColor: '#1E1E1E' },
          tabBarActiveTintColor: '#2196F3',
        }}
      >
        <Tab.Screen
          name="Home"
          component={DashboardScreen}
          options={{ title: 'Smart Stadium' }}
        />
      </Tab.Navigator>
    </NavigationContainer>
  );
};
