window.config = {
  routerBasename: "/",
  showStudyList: true,
  maxNumberOfWebWorkers: 3,
  extensions: [],
  modes: [
    "@ohif/mode-longitudinal",
  ],
  dataSources: [
    {
      namespace: "@ohif/extension-default.dataSourcesModule.dicomweb",
      sourceName: "orthanc",
      configuration: {
        friendlyName: "BRN Orthanc",
        name: "orthanc",
        qidoRoot: "/dicom-web",
        wadoRoot: "/dicom-web",
        wadoUriRoot: "/wado",
        qidoSupportsIncludeField: true,
        supportsReject: false,
        imageRendering: "wadors",
        thumbnailRendering: "wadors",
        enableStudyLazyLoad: true,
        supportsFuzzyMatching: false,
        supportsWildcard: true,
        staticWado: false,
        singlepart: "bulkdata,video"
      }
    }
  ],
  defaultDataSourceName: "orthanc"
};
