import React from 'react';
import { BrowserRouter as Router, Route, Switch } from 'react-router-dom';
import CollaborativeEditor from './components/CollaborativeEditor';

const App: React.FC = () => {
  return (
    <Router>
      <Switch>
        <Route path="/" exact component={CollaborativeEditor} />
      </Switch>
    </Router>
  );
};

export default App;