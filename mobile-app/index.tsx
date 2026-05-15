import React, { useEffect } from 'react';
import { AppRegistry, View, Text, StyleSheet } from 'react-native';
import { AppNavigator } from './src/navigation/AppNavigator';
import { ssepService } from './src/services/SSEPService';
import messaging from '@react-native-firebase/messaging';

const appName = 'SSEPAttendeeApp';

function App() {
  useEffect(() => {
    ssepService.requestNotificationPermission().then(granted => {
      if (granted) {
        messaging().onMessage(async remoteMessage => {
          console.log('Foreground notification:', remoteMessage);
        });
        messaging().setBackgroundMessageHandler(async remoteMessage => {
          console.log('Background notification:', remoteMessage);
        });
      }
    });
  }, []);

  return <AppNavigator />;
}

AppRegistry.registerComponent(appName, () => App);

export default App;
