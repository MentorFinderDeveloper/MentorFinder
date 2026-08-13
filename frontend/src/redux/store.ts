import { configureStore } from "@reduxjs/toolkit";

import authReducer from "./auth";

// Register the app's Redux reducers in one root store shared by the entire frontend.
const store = configureStore({
    reducer: {
        auth: authReducer,
    },
});

// RootState is used by selectors to type the shape of the Redux tree.
export type RootState = ReturnType<typeof store.getState>;
// AppDispatch is used when components need a typed dispatch function.
export type AppDispatch = typeof store.dispatch;
export default store;
